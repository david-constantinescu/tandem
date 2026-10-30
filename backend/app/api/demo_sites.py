"""Tandem's simulated booking websites (served at /demo-sites/<kind>/).

They are ordinary multi-page HTML sites — search form, results, passenger details, payment, confirmation —
so the browser agent navigates them exactly as it would a real site. Offers travel between pages in a
signed token, and the confirmation page is the "provider record" the agent reads back to verify a booking.
Everything is fictional; no card details are requested and nothing is charged.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, current_app, request

bp = Blueprint("demo_sites", __name__, url_prefix="/demo-sites")

KINDS = {
    "rail": {"name": "Ferrovia Demo", "noun": "train", "colour": "#1b524c", "prefix": "FD", "base": 29, "mins": (95, 260),
             "carrier": "FD"},
    "coach": {"name": "CoachLine Demo", "noun": "coach", "colour": "#a94f2d", "prefix": "CL", "base": 14, "mins": (180, 480),
              "carrier": "CL"},
    "air": {"name": "AeroDemo", "noun": "flight", "colour": "#33484c", "prefix": "AD", "base": 49, "mins": (80, 190),
            "carrier": "AD"},
    "museum": {"name": "MuseoPass Demo", "noun": "ticket", "colour": "#5b4bb5", "prefix": "MP", "base": 18, "mins": (120, 120),
               "carrier": ""},
}
VENUES = [
    ("galleria-demo-roma", "Galleria Demo d'Arte Moderna", "Rome", "Via Demo 1, 00197 Rome", 18),
    ("museo-demo-storia", "Museo Demo di Storia Antica", "Rome", "Piazza Demo 4, 00186 Rome", 15),
    ("musee-demo-paris", "Musée Démo des Beaux-Arts", "Paris", "1 Rue Démo, 75007 Paris", 17),
    ("demo-gallery-london", "Demo Gallery of Modern Art", "London", "1 Demo Street, London SE1", 0),
    ("museu-demo-lisboa", "Museu Demo do Azulejo", "Lisbon", "Rua Demo 8, 1100-001 Lisbon", 12),
]


def _sign(payload: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode().rstrip("=")
    sig = hmac.new(current_app.config["SECRET_KEY"].encode(), raw.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{raw}.{sig}"


def _verify(token: str) -> dict:
    try:
        raw, sig = token.rsplit(".", 1)
    except ValueError:
        abort(400)
    good = hmac.new(current_app.config["SECRET_KEY"].encode(), raw.encode(), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(sig, good):
        abort(400)
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def _page(kind: str, title: str, body: str) -> tuple[str, int, dict]:
    k = KINDS[kind]
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · {k['name']}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#faf8f4;color:#14262a}}
header{{background:{k['colour']};color:#fff;padding:18px 24px}}header b{{font-size:20px}}
.notice{{background:#fbf3dc;color:#8a5a08;padding:8px 24px;font-size:13px}}main{{max-width:760px;margin:24px auto;padding:0 16px}}
label{{display:block;font-size:13px;margin:10px 0 4px}}input,select{{padding:9px;border:1px solid #cfc1aa;border-radius:8px;width:100%;box-sizing:border-box}}
button{{background:{k['colour']};color:#fff;border:0;padding:10px 16px;border-radius:8px;margin-top:12px;cursor:pointer}}
article{{background:#fff;border:1px solid #e2d8c7;border-radius:12px;padding:14px;margin:10px 0}}dl{{display:grid;grid-template-columns:150px 1fr;gap:6px}}dt{{color:#5b6d70}}</style>
</head><body><header><b>{k['name']}</b> · simulated {k['noun']} booking site</header>
<div class="notice">Simulated website used by Tandem demos. Nothing is real: no tickets are issued and no payment is taken.</div>
<main><h1>{html.escape(title)}</h1>{body}</main></body></html>"""
    return doc, 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}


def _kind(kind: str) -> dict:
    if kind not in KINDS:
        abort(404)
    return KINDS[kind]


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest(), 16)


def _offers(kind: str, origin: str, destination: str, day: str, adults: int) -> list[dict]:
    k = KINDS[kind]
    s = _seed(kind, origin.lower(), destination.lower())
    lo, hi = k["mins"]
    duration = lo + s % (hi - lo + 1)
    starts = ["06:40", "08:15", "10:50", "13:20", "16:05", "18:45"]
    offers = []
    for i, start in enumerate(starts):
        if (s >> (i + 3)) % 5 == 0:
            continue  # not every departure runs every day
        h, m = map(int, start.split(":"))
        dep = datetime.fromisoformat(f"{day}T{h:02d}:{m:02d}")
        arr = dep + timedelta(minutes=duration + (i % 2) * 10)
        price = round(k["base"] + (s >> (i * 4)) % 40 + (12 if 7 <= h <= 9 or 16 <= h <= 18 else 0), 2)
        offers.append({
            "kind": kind, "offer_id": f"{k['carrier']}{100 + (s >> i) % 800}", "origin": origin, "destination": destination,
            "date": day, "depart": dep.strftime("%H:%M"), "arrive": arr.strftime("%H:%M"),
            "arrive_date": arr.date().isoformat(), "duration_min": int((arr - dep).total_seconds() // 60),
            "unit_price": price, "adults": adults, "total": round(price * adults, 2), "currency": "EUR",
        })
    return offers


def _museum_offers(venue_key: str, day: str, adults: int) -> list[dict]:
    venue = next((v for v in VENUES if v[0] == venue_key), None)
    if venue is None:
        return []
    key, name, city, address, price = venue
    out = []
    for hour in range(9, 18):
        remaining = _seed(key, day, hour) % 12
        if remaining == 0:
            continue
        out.append({"kind": "museum", "offer_id": f"{key}-{hour:02d}", "venue": name, "venue_key": key, "city": city,
                    "address": address, "date": day, "depart": f"{hour:02d}:00", "arrive": f"{hour + 2:02d}:00",
                    "arrive_date": day, "duration_min": 120, "unit_price": float(price), "adults": adults,
                    "total": round(price * adults, 2), "currency": "EUR", "remaining": remaining})
    return out


@bp.get("/<kind>/")
def home(kind):
    k = _kind(kind)
    today = date.today().isoformat()
    if kind == "museum":
        options = "".join(f'<option value="{v[0]}">{html.escape(v[1])} — {v[2]}</option>' for v in VENUES)
        form = f"""<form id="search" method="get" action="/demo-sites/{kind}/results">
<label for="venue">Museum or gallery</label><select id="venue" name="venue">{options}</select>
<label for="date">Visit date</label><input id="date" name="date" type="date" min="{today}" required>
<label for="adults">Visitors</label><input id="adults" name="adults" type="number" min="1" max="9" value="1">
<button type="submit">Find time slots</button></form>"""
    else:
        form = f"""<form id="search" method="get" action="/demo-sites/{kind}/results">
<label for="origin">From</label><input id="origin" name="origin" placeholder="City" required>
<label for="destination">To</label><input id="destination" name="destination" placeholder="City" required>
<label for="date">Date</label><input id="date" name="date" type="date" min="{today}" required>
<label for="adults">Passengers</label><input id="adults" name="adults" type="number" min="1" max="9" value="1">
<button type="submit">Search {k['noun']}s</button></form>"""
    return _page(kind, f"Book a {k['noun']}", form)


@bp.get("/<kind>/results")
def results(kind):
    _kind(kind)
    day = request.args.get("date", "")
    try:
        date.fromisoformat(day)
        adults = max(1, min(9, int(request.args.get("adults", "1") or 1)))
    except ValueError:
        return _page(kind, "Please check your search", '<p>Enter a valid date and number of travellers. <a href="./">Back</a></p>')
    if kind == "museum":
        offers = _museum_offers(request.args.get("venue", ""), day, adults)
        heading = f"Time slots on {day}"
    else:
        origin, destination = request.args.get("origin", "").strip(), request.args.get("destination", "").strip()
        if not origin or not destination:
            return _page(kind, "Please check your search", '<p>Enter where you travel from and to. <a href="./">Back</a></p>')
        offers = _offers(kind, origin, destination, day, adults)
        heading = f"{html.escape(origin)} → {html.escape(destination)} on {day}"
    if not offers:
        return _page(kind, heading, "<p>No availability on this date.</p>")
    items = []
    for o in offers:
        label = (f"{o['depart']} entry · {o['remaining']} left" if kind == "museum"
                 else f"{o['offer_id']} · {o['depart']} → {o['arrive']} · {o['duration_min'] // 60}h{o['duration_min'] % 60:02d}")
        items.append(f"""<article class="offer" data-offer-id="{o['offer_id']}" data-depart="{o['depart']}" data-arrive="{o['arrive']}"
 data-price="{o['unit_price']}" data-total="{o['total']}" data-currency="EUR"><h2>{html.escape(label)}</h2>
<p>€{o['unit_price']:.2f} per person · total €{o['total']:.2f}</p>
<form method="get" action="/demo-sites/{kind}/select"><input type="hidden" name="token" value="{_sign(o)}">
<button type="submit" name="pick" value="{o['offer_id']}">Select {o['depart']}</button></form></article>""")
    return _page(kind, heading, "".join(items))


@bp.get("/<kind>/select")
def select(kind):
    k = _kind(kind)
    o = _verify(request.args.get("token", ""))
    rows = []
    for i in range(1, o["adults"] + 1):
        rows.append(f"""<label for="first_name_{i}">{'Visitor' if kind == 'museum' else 'Passenger'} {i} first name</label>
<input id="first_name_{i}" name="first_name_{i}" autocomplete="given-name" required>
<label for="last_name_{i}">{'Visitor' if kind == 'museum' else 'Passenger'} {i} last name</label>
<input id="last_name_{i}" name="last_name_{i}" autocomplete="family-name" required>""")
    summary = _summary(kind, o)
    body = f"""{summary}<form id="details" method="post" action="/demo-sites/{kind}/pay">
<input type="hidden" name="token" value="{request.args.get('token')}">{''.join(rows)}
<label for="email">Email for the {k['noun']} (optional)</label><input id="email" name="email" type="email" autocomplete="email">
<button type="submit">Continue to payment</button></form>"""
    return _page(kind, "Who is travelling?" if kind != "museum" else "Who is visiting?", body)


def _summary(kind: str, o: dict) -> str:
    what = (f"{html.escape(o['venue'])}, {o['date']} at {o['depart']}" if kind == "museum"
            else f"{o['offer_id']} {html.escape(o['origin'])} → {html.escape(o['destination'])}, {o['date']} {o['depart']}–{o['arrive']}")
    return f'<article id="summary"><p>{what}</p><p>{o["adults"]} × €{o["unit_price"]:.2f} = <b>€{o["total"]:.2f}</b></p></article>'


def _names(form, adults: int) -> list[str]:
    names = []
    for i in range(1, adults + 1):
        first, last = form.get(f"first_name_{i}", "").strip(), form.get(f"last_name_{i}", "").strip()
        if not first or not last:
            abort(400)
        names.append(f"{first} {last}")
    return names


@bp.post("/<kind>/pay")
def pay(kind):
    _kind(kind)
    token = request.form.get("token", "")
    o = _verify(token)
    names = _names(request.form, o["adults"])
    hidden = "".join(f'<input type="hidden" name="{k}" value="{html.escape(v)}">' for k, v in request.form.items() if k != "token")
    body = f"""{_summary(kind, o)}<p>Travellers: {html.escape(', '.join(names))}</p>
<p><i>Simulated payment — this site never asks for card details.</i></p>
<form id="payment" method="post" action="/demo-sites/{kind}/confirm"><input type="hidden" name="token" value="{token}">{hidden}
<button type="submit" name="pay" value="{o['total']:.2f}" data-total="{o['total']:.2f}">Pay €{o['total']:.2f} (simulated)</button></form>"""
    return _page(kind, "Payment", body)


@bp.post("/<kind>/confirm")
def confirm(kind):
    k = _kind(kind)
    token = request.form.get("token", "")
    o = _verify(token)
    names = _names(request.form, o["adults"])
    ref = k["prefix"] + "-" + hmac.new(current_app.config["SECRET_KEY"].encode(), (token + "|".join(names)).encode(),
                                        hashlib.sha256).hexdigest()[:6].upper()
    where = html.escape(o.get("venue") or f"{o['origin']} → {o['destination']}")
    attrs = {"ref": ref, "kind": kind, "offer": o["offer_id"], "date": o["date"], "depart": o["depart"], "arrive": o["arrive"],
             "arrive-date": o["arrive_date"], "total": f"{o['total']:.2f}", "currency": o["currency"], "adults": str(o["adults"]),
             "origin": o.get("origin", ""), "destination": o.get("destination", ""), "venue": o.get("venue", ""),
             "address": o.get("address", ""), "city": o.get("city", ""), "passengers": "; ".join(names)}
    data_attrs = " ".join(f'data-{k_}="{html.escape(str(v))}"' for k_, v in attrs.items())
    body = f"""<section id="confirmation" {data_attrs}><p><b>Your booking is confirmed (simulated).</b></p>
<dl><dt>Booking reference</dt><dd>{ref}</dd><dt>{'Visit' if kind == 'museum' else 'Journey'}</dt><dd>{where}</dd>
<dt>Date</dt><dd>{o['date']}</dd><dt>{'Entry' if kind == 'museum' else 'Departs'}</dt><dd>{o['depart']}</dd>
<dt>{'Until' if kind == 'museum' else 'Arrives'}</dt><dd>{o['arrive']}</dd><dt>Travellers</dt><dd>{html.escape(', '.join(names))}</dd>
<dt>Total paid</dt><dd>€{o['total']:.2f} (simulated)</dd><dt>Status</dt><dd>Confirmed</dd></dl></section>"""
    return _page(kind, "Booking confirmed", body)
