"""Deterministic trip grouping.

A record joins an existing trip only with corroborating evidence: overlapping/adjacent dates *and*
a destination or geographic match, or a shared booking reference. Similar dates alone never
group records. Every decision stores its score and reasons so the UI can explain it and users
can move records afterwards.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.extensions import db
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
    """City that represents where the traveller *is* for this record."""
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
    reasons: list[str] = []
    score = 0.0
    start, end = record_dates(data)
    ref = _norm(data.get("booking_reference"))
    if ref:
        shared = db.session.execute(
            db.select(Reservation.booking_reference).where(Reservation.trip_id == trip.id,
                                                           Reservation.booking_reference.is_not(None))
        ).scalars().all()
        if any(_norm(r) == ref for r in shared):
            score += 0.6
            reasons.append(f"Shares booking reference {data.get('booking_reference')}")

    date_ok = False
    if start and trip.start_date and trip.end_date:
        lo, hi = trip.start_date - timedelta(days=1), trip.end_date + timedelta(days=1)
        if lo <= start <= hi or (end and lo <= end <= hi):
            score += 0.35
            date_ok = True
            reasons.append(f"Dates fall within the trip ({trip.start_date:%d %b} – {trip.end_date:%d %b})")
        elif trip.start_date - timedelta(days=4) <= start <= trip.end_date + timedelta(days=4):
            score += 0.15
            date_ok = True
            reasons.append("Dates are within a few days of the trip")

    city, lat, lon = record_destination(data, user)
    place_ok = False
    for name, plat, plon in trip_places(trip):
        if city and _norm(name) and (_norm(name) == _norm(city) or _norm(city) in _norm(name)):
            score += 0.4
            place_ok = True
            reasons.append(f"Same destination ({city})")
            break
        if lat is not None and plat is not None and geo.haversine_km(lat, lon, plat, plon) < 60:
            score += 0.35
            place_ok = True
            reasons.append(f"Within 60 km of {name}")
            break
    # Outbound/return flights from home: the home-side city matches via arrival/departure city above.
    names = {_norm(n) for n in data.get("travellers") or []}
    if names and any(_norm(t.full_name) in names for t in trip.travellers):
        score += 0.05
        reasons.append("Same traveller")
    ref_match = any(r.startswith("Shares booking reference") for r in reasons)
    if ref_match:
        return round(min(score, 1.0), 2), reasons
    if not date_ok:
        return min(score, 0.4), reasons + ["Dates do not match"]
    if not place_ok:
        # Similar dates alone are never enough to group records.
        return min(score, 0.3), reasons + ["No destination match"]
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
    name = f"{city} trip" if city else "New trip"
    if start:
        name = f"{city or 'Trip'} · {start:%b %Y}" if city else f"Trip · {start:%b %Y}"
    return {
        "action": "create", "score": best[0], "reasons": (best[2] if best[1] else []) or ["No matching trip found"],
        "closest_trip_id": str(best[1].id) if best[1] else None,
        "new_trip": {"name": name, "destination": city, "lat": lat, "lon": lon,
                     "start_date": start.isoformat() if start else None,
                     "end_date": (end or start).isoformat() if start else None},
    }
