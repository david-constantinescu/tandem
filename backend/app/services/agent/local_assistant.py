"""asistentul offline, cand nu avem ai (fara chei sau fara voie). raspunde la intrebarile uzuale din date"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

from app.i18n import When, locale_of, long_date, tr
from app.services.agent.tools import ToolContext, _next_trip, run_tool, today_for
from app.services.ingestion.dates import find_dates

# weekday names, Monday first; Romanian ones are matched without diacritics
WEEKDAYS = [("monday", "luni"), ("tuesday", "marti"), ("wednesday", "miercuri"), ("thursday", "joi"),
            ("friday", "vineri"), ("saturday", "sambata"), ("sunday", "duminica")]
MONTHS = [("jan", "ian"), ("feb", "feb"), ("mar", "mar"), ("apr", "apr"), ("may", "mai"), ("jun", "iun"),
          ("jul", "iul"), ("aug", "aug"), ("sep", "sep"), ("oct", "oct"), ("nov", "noi"), ("dec", "dec")]
CATEGORY_WORDS = {"museum": "museums", "muzeu": "museums", "gallery": "museums", "galeri": "museums",
                  "tour": "tours", "tur": "tours", "walking": "tours", "pe jos": "tours", "food": "food",
                  "eat": "food", "mancare": "food", "cooking": "workshops", "gatit": "workshops",
                  "workshop": "workshops", "atelier": "workshops", "class": "workshops", "curs": "workshops",
                  "outdoor": "outdoor", "aer liber": "outdoor", "bike": "outdoor", "bicicl": "outdoor",
                  "history": "historical", "historic": "historical", "istori": "historical",
                  "show": "entertainment", "spectacol": "entertainment", "nightlife": "entertainment",
                  "day trip": "day trips", "excursie": "day trips"}
SITE_FOR = {"train": "demo_rail", "tren": "demo_rail", "rail": "demo_rail", "bus": "demo_coach", "autobuz": "demo_coach",
            "coach": "demo_coach", "autocar": "demo_coach", "flight": "demo_air", "plane": "demo_air", "zbor": "demo_air",
            "avion": "demo_air", "museum": "demo_museum", "muzeu": "demo_museum", "gallery": "demo_museum",
            "galerie": "demo_museum"}
# "from Rome to Florence on Sunday" / "de la Roma la Florenta cu trenul pe 14 noiembrie"
ROUTE = (r"(?:from|de la|din) ([a-z .'-]+?) (?:to|la|spre|catre|pana la|in) ([a-z .'-]+?)"
         r"(?: on| for| at| by| with| this| next| pe| pentru| in| cu| duminica| luni| marti| miercuri| joi| vineri| sambata"
         r"|,|\.|\?|$)")
CATEGORY_FOR = {"demo_rail": "train", "demo_coach": "bus", "demo_air": "flight", "demo_museum": "museum"}
STATUS = {"confirmed": "confirmed", "pending": "pending", "unknown": "unconfirmed", "suggested": "suggestion",
          "unbooked": "not booked", "cancelled": "cancelled", "completed": "completed"}
SEVERITY = {"critical": "critical", "warning": "warning", "info": "info"}
CONDITIONS = {"clear": "clear", "cloudy": "cloudy", "fog": "fog", "drizzle": "drizzle", "rain": "rain", "snow": "snow",
              "storm": "storms", "unknown": "unknown"}
NEWS_KINDS = {"strike": "Strike", "protest": "Protest or march", "weather": "Weather alert", "closure": "Closure",
              "news": "News"}


def _plain(text: str) -> str:
    """lower case without diacritics, so "sâmbătă" and "sambata" match alike"""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _fmt_time(iso_value: str | None, loc: str) -> str:
    if not iso_value:
        return ""
    return When(datetime.fromisoformat(iso_value)).render(loc)


def _resolve_day(text: str, user, trip_start: date | None, trip_end: date | None) -> date | None:
    t = _plain(text)
    today = today_for(user)
    if re.search(r"tomorrow|maine", t):
        return today + timedelta(days=1)
    if re.search(r"today|tonight|\bazi\b|astazi|diseara", t):
        return today
    hits = find_dates(text)
    if hits:
        return hits[0].value
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*\b", t)
    if m:
        month = next((i + 1 for i, names in enumerate(MONTHS) if m.group(2) in names), None)
        if month:
            year = today.year if month >= today.month else today.year + 1
            try:
                return date(year, month, int(m.group(1)))
            except ValueError:
                return None
    for i, names in enumerate(WEEKDAYS):
        if any(re.search(rf"\b{n}\b", t) for n in names):
            start = trip_start if trip_start and trip_start > today else today
            for offset in range(0, 14):
                d = start + timedelta(days=offset)
                if d.weekday() == i and (trip_end is None or d <= trip_end or offset >= 7):
                    return d
    return None


_DAY_WORDS = (r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today|tonight|luni|marti|miercuri"
              r"|joi|vineri|sambata|duminica|maine|azi|astazi|diseara")
_MONTH_WORDS = "|".join(sorted({m for pair in MONTHS for m in pair}))


def _event_title(text: str) -> str:
    """"Add dinner at Roscioli on Saturday at 20:00" → "Dinner at Roscioli"."""
    t = _plain(text)
    keep = [True] * len(t)  # _plain keeps length for Romanian/Latin text, so spans map back onto the original
    for pattern in (r"^\s*(add|put|schedule|plan|adauga|pune|programeaza|planifica)\s+(an?\s+|un\s+|o\s+)?",
                    rf"\s*\b(on|pe|this|next|in|for)?\s*\b({_DAY_WORDS})\b",
                    rf"\s*\b(on|pe)?\s*\b\d{{1,2}}\s+({_MONTH_WORDS})[a-z]*\b",
                    r"\s*\b(at|la|ora|@)\s*\d{1,2}([:.]\d{2})?\s*(am|pm)?\b", r"\s*\b\d{1,2}[:.]\d{2}\b",
                    r"\s*\b(to|in|la)\s+(my\s+|the\s+|our\s+)?(plan|planul|itinerar\w*|itinerary|program\w*)\b"):
        for m in re.finditer(pattern, t):
            for i in range(m.start(), m.end()):
                keep[i] = False
    src = text if len(text) == len(t) else t
    title = re.sub(r"\s+", " ", "".join(c for c, k in zip(src, keep) if k)).strip(" ,.!?;:-")
    return title[:1].upper() + title[1:120]


def answer(user, ctx: ToolContext, text: str, tool_log: list, *, reason: str) -> str:
    lower = _plain(text)
    loc = locale_of(user)
    header = tr("_Offline assistant — {reason}. I can answer common questions from your trip data._", loc,
                reason=tr(reason, loc)) + "\n\n"

    def call(name: str, **kwargs):
        status, result = run_tool(ctx, name, kwargs)
        tool_log.append({"name": name, "status": status, "permission": "read", "args": kwargs,
                         "summary": "Done" if status == "ok" else str(result.get("error"))})
        return result if status == "ok" else None

    trip = _next_trip(user) if not ctx.default_trip_id else None
    trip_info = call("get_trip", trip_id=str(ctx.default_trip_id) if ctx.default_trip_id else (str(trip.id) if trip else None)) \
        if (ctx.default_trip_id or trip) else None
    if not trip_info:
        return header + tr("You don't have any trips yet. Add a booking confirmation to get started.", loc)
    tid = trip_info["trip_id"]
    t_start = date.fromisoformat(trip_info["start_date"]) if trip_info.get("start_date") else None
    t_end = date.fromisoformat(trip_info["end_date"]) if trip_info.get("end_date") else None
    status_word = lambda s: tr(STATUS.get(s, s), loc)  # noqa: E731

    if re.search(r"unconfirm|not confirmed|pending|still need to book|neconfirm|nu (e|este) confirmat|in asteptare"
                 r"|trebuie sa rezerv", lower):
        res = call("get_reservations", trip_id=tid) or []
        open_items = [r for r in res if r["status"] != "confirmed"]
        if not open_items:
            return header + tr("Everything booked for **{trip}** shows as confirmed.", loc, trip=trip_info["name"])
        lines = [f"- **{r['title']}** — {status_word(r['status'])}" + (f", {_fmt_time(r['start_local'], loc)}" if r["start_local"] else "")
                 for r in open_items]
        return header + tr("Not confirmed yet on **{trip}**:", loc, trip=trip_info["name"]) + "\n" + "\n".join(lines)

    if re.search(r"conflict|clash|overlap|problem|issue|enough time|tight|suprapun|destul timp|timp suficient|strans"
                 r"|de rezolvat", lower):
        items = call("detect_conflicts", trip_id=tid) or []
        if not items:
            return header + tr("I didn't find any conflicts in this itinerary.", loc)
        lines = [f"- **{c['title']}** ({tr(SEVERITY.get(c['severity'], c['severity']), loc)}): {c['detail']}" for c in items[:8]]
        return header + tr("I found {n} things to look at:", loc, n=len(items)) + "\n" + "\n".join(lines)

    add = re.match(r"\s*(add|put|schedule|plan|adauga|pune|programeaza|planifica)\b", lower)
    at = re.search(r"\b(?:at|la|ora|@)\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b|\b(\d{1,2})[:.](\d{2})\b", lower)
    if add and at:
        day = _resolve_day(text, user, t_start, t_end)
        if not day:
            return header + tr("Which day? e.g. *on Sunday* or *on 15 November*.", loc)
        hour, minute = int(at.group(1) or at.group(4)), int(at.group(2) or at.group(5) or 0)
        if at.group(3) == "pm" and hour < 12:
            hour += 12
        title = _event_title(text)
        if not title or hour > 23 or minute > 59:
            return header + tr("Tell me what and when, e.g. *add dinner at Roscioli on Saturday at 20:00*.", loc)
        kind = "restaurant" if re.search(r"dinner|lunch|breakfast|brunch|cina|pranz|mic dejun|restaurant|trattoria|osteria"
                                         r"|pizz|cafe|gelat|aperitiv|drinks|bar\b", lower) else "activity"
        start = datetime(day.year, day.month, day.day, hour, minute)
        end = start + timedelta(minutes=90 if kind == "restaurant" else 60)  # a sensible length, so clashes show
        made = call("create_itinerary_event", trip_id=tid, title=title, type=kind, requested_by_user=True,
                    start_local=start.strftime("%Y-%m-%dT%H:%M"), end_local=end.strftime("%Y-%m-%dT%H:%M"))
        if not made:
            return header + tr("I couldn't add that to the plan.", loc)
        out = header + tr("Added **{title}** to your plan: {when}.", loc, title=title,
                          when=_fmt_time(made["created"]["start_local"], loc))
        clashes = [c for c in (call("detect_conflicts", trip_id=tid) or []) if title.lower() in c["title"].lower()]
        if clashes:
            out += "\n\n" + tr("Heads up:", loc) + "\n" + "\n".join(f"- **{c['title']}**: {c['detail']}" for c in clashes[:3])
        return out

    booking = re.search(r"\b(book|buy|get|rezerva|cumpara|ia-mi|ia|ajung\w*|merg\w*|go|travel|calatoresc)\b.*"
                        r"\b(train|tren|rail|bus|autobuz|coach|autocar|flight|zbor|plane|avion|museum|muzeu|gallery"
                        r"|galerie)\w*", lower)
    practice = re.search(r"practice|simulat|exersa|test", lower)
    route = re.search(ROUTE, lower)
    asks_way = route and re.search(r"how (do|can|should|would) (i|we)|get (to|from|there)|cum (ajung|ajungem|merg|mergem)"
                                   r"|\bdrum|calatori", lower)
    if ((booking and SITE_FOR[booking.group(2)] != "demo_museum") or asks_way) and not practice:
        if not route:
            return header + tr("Tell me where from and to, e.g. *book a train from Rome to Florence on Sunday*.", loc)
        day = _resolve_day(text, user, t_start, t_end)
        mode = {"demo_rail": "train", "demo_coach": "bus", "demo_air": "flight"}.get(SITE_FOR[booking.group(2)]) if booking else None
        origin, destination = route.group(1).strip().title(), route.group(2).strip().title()
        result = call("plan_journey", origin=origin, destination=destination, mode=mode,
                      date=day.isoformat() if day else None) or {"links": []}
        lines = [f"- [{link['name']}]({link['url']})" for link in result["links"][:6]]
        news = call("check_local_news", trip_id=tid, date=day.isoformat() if day else None) or {"items": []}
        # only strikes that name the travel day; older strike reports are about other days
        strikes = [i for i in news.get("items", []) if i["kind"] == "strike" and (i["mentions_dates"] or not day)][:2]
        warn = ""
        if strikes:
            warn = "\n\n" + tr("Heads up — recent news about strikes:", loc) + "\n" + "\n".join(
                f"- [{i['title']}]({i['url']}) · {i['source']}" for i in strikes)
        when = " " + tr("on {day}", loc, day=long_date(day, loc)) if day else ""
        return header + tr("Here's where to book {mode} {origin} → {destination}{when} on the real websites, with the route "
                           "filled in where the site allows it:", loc, mode=tr(mode or "tickets", loc), origin=origin,
                           destination=destination, when=when) + "\n" + "\n".join(lines) + warn + "\n\n" + \
            tr("Book there, then forward the confirmation to Tandem and I'll add it to your trip.", loc)

    # word boundaries matter: "rain" is inside "train" and "hot" inside "hotel"
    if re.search(r"weather|\brain|forecast|umbrella|\bcold\b|\bhot\b|vreme|ploua|ploaie|prognoz|umbrel|\bfrig|\bcald|temperatur", lower):
        day = _resolve_day(text, user, t_start, t_end)
        w = call("get_weather", trip_id=tid, date=day.isoformat() if day else None) or {}
        if not w.get("available"):
            if w.get("reason") == "too_far_ahead":
                return header + tr("The forecast only reaches 16 days ahead. Ask me again from {day}.", loc,
                                   day=long_date(date.fromisoformat(w["forecast_from"]), loc))
            return header + tr("I couldn't get the weather right now.", loc)
        lines, wet = [], []
        for d in w["days"]:
            dd = date.fromisoformat(d["date"])
            temps = f"{round(d['temp_min'])}–{round(d['temp_max'])}°C" if d["temp_max"] is not None else ""
            rain = tr("{p}% chance of rain", loc, p=d["precip_probability"]) if d["precip_probability"] is not None else ""
            verdict = tr("good for outdoors", loc) if d["outdoor_ok"] else tr("better indoors", loc)
            lines.append(f"- **{long_date(dd, loc)}**: {tr(CONDITIONS.get(d['condition'], d['condition']), loc)}, "
                         f"{temps}, {rain} — {verdict}")
            if not d["outdoor_ok"]:
                wet.append(dd)
        out = header + tr("Weather in {place} (Open-Meteo):", loc, place=w.get("place") or "") + "\n" + "\n".join(lines)
        if wet:
            pick = call("search_activities", trip_id=tid, date=wet[0].isoformat(), categories=["museums"]) or {"results": []}
            indoor = [r["title"] for r in pick.get("results", []) if r.get("weather_note") != "outdoor_in_bad_weather"][:3]
            out += "\n\n" + tr("On {day} keep outdoor plans short.", loc, day=long_date(wet[0], loc))
            if indoor:
                out += " " + tr("Indoor ideas: {names}.", loc, names=", ".join(indoor))
        return out

    if re.search(r"strike|protest|\bmarch\b|\bnews\b|closure|closed|disruption|\bbus\b|metro|greva|manifest|corteo|"
                 r"stiri|inchis|trafic|autobuz|transport", lower):
        day = _resolve_day(text, user, t_start, t_end)
        news = call("check_local_news", trip_id=tid, date=day.isoformat() if day else None) or {"items": []}
        items = news.get("items", [])
        if not news.get("available"):
            return header + tr("I couldn't check the local news right now.", loc)
        if not items:
            return header + tr("I found no recent news about strikes, protests or closures in {place}.", loc,
                               place=news.get("place") or "")
        lines = [f"- **{tr(NEWS_KINDS.get(i['kind'], 'News'), loc)}**: [{i['title']}]({i['url']}) · {i['source']}"
                 + (" — " + tr("mentions your trip dates", loc) if i["mentions_dates"] else "") for i in items[:6]]
        on_dates = [i for i in items if i["mentions_dates"]]
        verdict = tr("{n} of these mention your trip dates — plan around them.", loc, n=len(on_dates)) if on_dates else \
            tr("None of these mention your trip dates, so they look like they're about other days.", loc)
        return header + tr("Recent local news for {place} ({source}):", loc, place=news.get("place") or "",
                           source=news.get("source") or "") + "\n" + "\n".join(lines) + "\n\n" + verdict + " " + \
            tr("These are news reports, not confirmed timetables: check the operator's site on the day.", loc)

    if booking:
        site = SITE_FOR[booking.group(2)]
        if not user.is_demo:
            sites = call("list_booking_websites", category=CATEGORY_FOR[site]) or []
            names = ", ".join(s["name"] for s in sites if s["policy"] != "simulated")[:400]
            return header + tr("Real booking sites are link-only for now ({names}). Open one from **Explore → Tickets**, "
                               "book there, then forward the confirmation to Tandem and I'll add it to your trip.", loc, names=names)
        day = _resolve_day(text, user, t_start, t_end)
        route = re.search(ROUTE, lower)
        party = re.search(r"\b(\d) (?:people|persons|adults|tickets|of us|persoane|oameni|adulti|bilete)\b", lower)
        args = {"site": site, "date": day.isoformat() if day else None, "trip_id": tid,
                "adults": int(party.group(1)) if party else max(1, len(trip_info.get("travellers") or []) or 1)}
        if site == "demo_museum":
            city = re.search(r"paris|london|londra|lisbon|lisabona", lower)
            args["venue"] = "Galleria Demo" if not city else \
                {"paris": "Musée", "london": "Demo Gallery", "londra": "Demo Gallery", "lisbon": "Azulejo", "lisabona": "Azulejo"}[city.group(0)]
        elif route:
            args["origin"], args["destination"] = route.group(1).strip().title(), route.group(2).strip().title()
        else:
            return header + tr("Tell me where from and to, e.g. *book a train from Rome to Florence on Sunday*.", loc)
        if not args["date"]:
            return header + tr("Which day? e.g. *on Sunday* or *on 15 November*.", loc)
        result = call("start_website_task", **{k: v for k, v in args.items() if v is not None})
        if not result:
            return header + tr("I couldn't start the website task.", loc)
        sel = result.get("selected") or {}
        if result["state"] == "awaiting_approval":
            return header + tr("The browser agent searched the simulated site and picked **{offer} {depart}–{arrive}** (€{total}). "
                               "It paused before entering any names — approve the card below to complete the (simulated) purchase.",
                               loc, offer=sel.get("offer_id", ""), depart=sel.get("depart", ""), arrive=sel.get("arrive", ""),
                               total=f"{sel.get('total', 0):.2f}")
        return header + tr("Website task: {state}. {note}", loc, state=result["state"].replace("_", " "), note=result.get("note") or "")

    if re.search(r"find|suggest|recommend|something to do|activit|museum|tour|things to do|gaseste|sugereaza|recomanda"
                 r"|ceva de facut|ce sa fac|muzeu|\btur\b", lower):
        day = _resolve_day(text, user, t_start, t_end)
        cats = sorted({c for w, c in CATEGORY_WORDS.items() if w in lower})
        result = call("search_activities", trip_id=tid, date=day.isoformat() if day else None, categories=cats)
        if not result or not result["results"]:
            unavailable = [p["name"] for p in (result or {}).get("providers", []) if p.get("error")]
            return header + tr("I couldn't find activities for that.", loc) + (
                " " + tr("Unavailable providers: {names}.", loc, names=", ".join(unavailable)) if unavailable else "")
        lines = []
        for r in result["results"][:5]:
            price = f"{r['price']:.0f} {r['currency']}" if r.get("price") is not None and r.get("currency") else tr("price unknown", loc)
            fit = r["fits"].get("status") if r.get("fits") else None
            fit_text = {"fits": tr("fits your free time", loc), "no_fitting_slot": tr("no time fits your plans", loc),
                        "availability_unknown": tr("availability not checked", loc)}.get(fit, "")
            slots = ", ".join(s["time"] for s in (r.get("fits") or {}).get("slots", [])[:3])
            lines.append(f"- **{r['title']}** · {price}" + (f" · {fit_text}" if fit_text else "")
                         + (" (" + tr("e.g. {times}", loc, times=slots) + ")" if slots else ""))
        intro = tr("Options on {day}:", loc, day=long_date(day, loc)) if day else tr("Options:", loc)
        return header + intro + "\n" + "\n".join(lines) + "\n\n" + \
            tr("Use **Prepare booking** on a card to get a live quote you can approve.", loc)

    if re.search(r"summar|before (departure|i leave|leaving)|what do i need|checklist|overview|rezum|inainte de plecare"
                 r"|de ce am nevoie|lista|pe scurt", lower):
        res = call("get_reservations", trip_id=tid) or []
        conflicts = call("detect_conflicts", trip_id=tid) or []
        lines = [f"**{trip_info['name']}** · {trip_info.get('start_date')} → {trip_info.get('end_date')}",
                 tr("Destinations: {names}", loc, names=", ".join(trip_info["destinations"]) or tr("not set", loc)), ""]
        for r in res:
            ref = f" · {tr('ref', loc)} {r['booking_reference']}" if r.get("booking_reference") else ""
            lines.append(f"- {tr(r['type'].replace('_', ' ').capitalize(), loc)}: **{r['title']}** — "
                         f"{_fmt_time(r['start_local'], loc)}{ref} ({status_word(r['status'])})")
        crit = [c for c in conflicts if c["severity"] in ("critical", "warning")]
        if crit:
            lines += ["", tr("Needs attention:", loc)] + [f"- {c['title']}" for c in crit[:5]]
        return header + "\n".join(lines)

    if re.search(r"delay|intarzi", lower):
        it = call("get_itinerary", trip_id=tid) or {"events": []}
        flights = [e for e in it["events"] if e["type"] in ("flight", "train")]
        if not flights:
            return header + tr("I don't see a flight or train in this trip.", loc)
        f = flights[0]
        later = [e for e in it["events"] if e["start_local"] and f["end_local"] and e["start_local"] > f["start_local"]][:4]
        lines = [tr("If **{title}** is delayed, the next plans after it are:", loc, title=f["title"])] + [
            f"- {e['title']} — {_fmt_time(e['start_local'], loc)}" for e in later if e["event_id"] != f["event_id"]]
        return header + "\n".join(lines) + "\n\n" + \
            tr("Tell me the new arrival time, or add the airline's update to Tandem.", loc)

    day = _resolve_day(text, user, t_start, t_end)
    if day or re.search(r"booked|plan|schedule|itinerary|what.*(have|doing)|rezervat|program|itinerar|ce am|ce fac", lower):
        it = call("get_itinerary", trip_id=tid, date=day.isoformat() if day else None) or {"events": []}
        events = it["events"]
        if not events:
            return header + (tr("Nothing is planned on {day}.", loc, day=long_date(day, loc)) if day
                             else tr("This trip has no itinerary events yet.", loc))
        title = long_date(day, loc) if day else trip_info["name"]
        lines = []
        for e in events[:15]:
            status = "" if e["status"] == "confirmed" else f" _({status_word(e['status'])})_"
            lines.append(f"- {_fmt_time(e['start_local'], loc)} — **{e['title']}**{status}")
        return header + f"**{title[0].upper() + title[1:]}**\n" + "\n".join(lines)

    return header + tr("I can tell you what's planned on a day, what's unconfirmed, check conflicts, summarise the "
                       "trip, or find activities that fit your free time. Connect an AI provider in Settings for "
                       "open-ended questions.", loc)
