"""grupeaza rezervarile in calatorii, dupa reguli simple"""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.extensions import db
from app.i18n import When, locale_of, month_year, tr
from app.models import Reservation, Trip, User
from app.services import geo
from app.utils.timeutil import parse_iso_datetime, to_local

JOIN_THRESHOLD = 0.6


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def record_dates(data: dict) -> tuple[date | None, date | None]:
    start = parse_iso_datetime(data.get("start_at"))
    end = parse_iso_datetime(data.get("end_at"))
    s = to_local(start, data.get("start_tz")).date() if start else None
    e = to_local(end, data.get("end_tz")).date() if end else s
    return s, e


def record_destination(data: dict, user: User) -> tuple[str | None, float | None, float | None]:
    """city that represents where the traveller *is* for this record"""
    home = _norm(user.home_city)
    if data.get("type") in ("flight", "train", "bus", "ferry"):
        end_city, start_city = data.get("end_city"), data.get("city")
        if end_city and (not home or _norm(end_city) != home):
            return end_city, data.get("end_lat"), data.get("end_lon")
        return start_city, data.get("lat"), data.get("lon")
    return data.get("city"), data.get("lat"), data.get("lon")


def trip_places(trip: Trip) -> list[tuple[str, float | None, float | None]]:
    places = [(d.name, d.lat, d.lon) for d in trip.destinations]
    if trip.primary_destination:
        places.append((trip.primary_destination, None, None))
    rows = db.session.execute(
        db.select(Reservation.city, Reservation.lat, Reservation.lon).where(Reservation.trip_id == trip.id)
    ).all()
    places.extend((r.city, r.lat, r.lon) for r in rows if r.city)
    return places


def score_trip(trip: Trip, data: dict, user: User) -> tuple[float, list[str]]:
    # reasons are shown to the user and stored with the proposal, so they're written in the user's language
    loc = locale_of(user)
    reasons: list[str] = []
    score = 0.0
    ref_match = False
    start, end = record_dates(data)
    ref = _norm(data.get("booking_reference"))
    if ref:
        shared = db.session.execute(
            db.select(Reservation.booking_reference).where(Reservation.trip_id == trip.id,
                                                           Reservation.booking_reference.is_not(None))
        ).scalars().all()
        if any(_norm(r) == ref for r in shared):
            score += 0.6
            ref_match = True
            reasons.append(tr("Shares booking reference {ref}", loc, ref=data.get("booking_reference")))

    date_ok = False
    if start and trip.start_date and trip.end_date:
        lo, hi = trip.start_date - timedelta(days=1), trip.end_date + timedelta(days=1)
        if lo <= start <= hi or (end and lo <= end <= hi):
            score += 0.35
            date_ok = True
            reasons.append(tr("Dates fall within the trip ({start} – {end})", loc,
                              start=When(trip.start_date, with_time=False), end=When(trip.end_date, with_time=False)))
        elif trip.start_date - timedelta(days=4) <= start <= trip.end_date + timedelta(days=4):
            score += 0.15
            date_ok = True
            reasons.append(tr("Dates are within a few days of the trip", loc))

    city, lat, lon = record_destination(data, user)
    place_ok = False
    for name, plat, plon in trip_places(trip):
        if city and _norm(name) and (_norm(name) == _norm(city) or _norm(city) in _norm(name)):
            score += 0.4
            place_ok = True
            reasons.append(tr("Same destination ({city})", loc, city=city))
            break
        if lat is not None and plat is not None and geo.haversine_km(lat, lon, plat, plon) < 60:
            score += 0.35
            place_ok = True
            reasons.append(tr("Within 60 km of {name}", loc, name=name))
            break
    # outbound/return flights from home: the home-side city matches via arrival/departure city above
    names = {_norm(n) for n in data.get("travellers") or []}
    if names and any(_norm(t.full_name) in names for t in trip.travellers):
        score += 0.05
        reasons.append(tr("Same traveller", loc))
    if ref_match:
        return round(min(score, 1.0), 2), reasons
    if not date_ok:
        return min(score, 0.4), reasons + [tr("Dates do not match", loc)]
    if not place_ok:
        # similar dates alone are never enough to group records
        return min(score, 0.3), reasons + [tr("No destination match", loc)]
    return round(min(score, 1.0), 2), reasons


def propose(user: User, data: dict) -> dict:
    trips = db.session.execute(
        db.select(Trip).where(Trip.user_id == user.id, Trip.is_cancelled.is_(False))
    ).scalars().all()
    best: tuple[float, Trip | None, list[str]] = (0.0, None, [])
    for trip in trips:
        score, reasons = score_trip(trip, data, user)
        if score > best[0]:
            best = (score, trip, reasons)
    if best[1] is not None and best[0] >= JOIN_THRESHOLD:
        return {"action": "join", "trip_id": str(best[1].id), "trip_name": best[1].name, "score": best[0],
                "reasons": best[2]}
    city, lat, lon = record_destination(data, user)
    start, end = record_dates(data)
    loc = locale_of(user)
    name = tr("{city} trip", loc, city=city) if city else tr("New trip", loc)
    if start:
        name = f"{city or tr('Trip', loc)} · {month_year(start, loc)}"
    return {
        "action": "create", "score": best[0], "reasons": (best[2] if best[1] else []) or [tr("No matching trip found", loc)],
        "closest_trip_id": str(best[1].id) if best[1] else None,
        "new_trip": {"name": name, "destination": city, "lat": lat, "lon": lon,
                     "start_date": start.isoformat() if start else None,
                     "end_date": (end or start).isoformat() if start else None},
    }
