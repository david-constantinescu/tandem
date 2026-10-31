"""cautarea de activitati la toti providerii, cu potrivire pe timpul liber si pe vreme"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from app.extensions import db
from app.models import ItineraryEvent, Reservation, Trip, User
from app.services import geo
from app.services.providers.base import (
    ActivityResult,
    ActivitySearchRequest,
    ProviderCapabilityError,
    ProviderRequestError,
)
from app.services.providers.registry import adapters_for
from app.utils.timeutil import localize, to_local

log = logging.getLogger("tandem.activities")

DAY_START, DAY_END = time(8, 30), time(22, 0)
BUFFER = timedelta(minutes=30)


def trip_timezone(trip: Trip) -> str:
    for d in trip.destinations:
        if d.timezone:
            return d.timezone
    ev = db.session.execute(db.select(ItineraryEvent.start_tz).where(ItineraryEvent.trip_id == trip.id).limit(1)).scalar()
    return ev or "UTC"


def free_windows(trip: Trip, day: date, tz: str | None = None) -> list[dict]:
    """free intervals on a local day, between 08:30 and 22:00, around existing (non-cancelled) events"""
    tz = tz or trip_timezone(trip)
    day_start, _ = localize(datetime.combine(day, DAY_START), tz)
    day_end, _ = localize(datetime.combine(day, DAY_END), tz)
    events = db.session.execute(db.select(ItineraryEvent).where(
        ItineraryEvent.trip_id == trip.id, ItineraryEvent.status.in_(["confirmed", "pending", "suggested"]),
        ItineraryEvent.start_at < day_end + timedelta(hours=12),
        ItineraryEvent.type.notin_(["free_time", "reminder"]))).scalars().all()
    busy = []
    for e in events:
        end = e.end_at or (e.start_at + timedelta(minutes=30))
        if end < day_start or e.start_at > day_end:
            continue
        busy.append((e.start_at - BUFFER, end + BUFFER, e))
    # leaving the city ends the day; arriving starts it
    busy.sort(key=lambda b: b[0])
    windows = []
    cursor = day_start
    for start, end, _ in busy:
        if start > cursor and (start - cursor) >= timedelta(minutes=60):
            windows.append((cursor, start))
        cursor = max(cursor, end)
    if day_end - cursor >= timedelta(minutes=60):
        windows.append((cursor, day_end))
    return [{"start": to_local(a, tz).isoformat(), "end": to_local(b, tz).isoformat(),
             "minutes": int((b - a).total_seconds() // 60)} for a, b in windows]


def _hotel_point(trip: Trip) -> tuple[float, float] | None:
    hotel = db.session.execute(db.select(Reservation).where(
        Reservation.trip_id == trip.id, Reservation.type == "hotel", Reservation.lat.is_not(None))).scalars().first()
    return (hotel.lat, hotel.lon) if hotel else None


def analyse_fit(result: ActivityResult, trip: Trip, days: list[date]) -> None:
    tz = trip_timezone(trip)
    windows_by_day = {d.isoformat(): free_windows(trip, d, tz) for d in days}
    fitting = []
    for slot in result.available_slots:
        if slot.get("remaining", 1) <= 0:
            continue
        win = windows_by_day.get(slot["date"])
        if win is None:
            continue
        start = datetime.fromisoformat(f"{slot['date']}T{slot['time']}")
        end = start + timedelta(minutes=result.duration_minutes or 60)
        for w in win:
            ws = datetime.fromisoformat(w["start"]).replace(tzinfo=None)
            we = datetime.fromisoformat(w["end"]).replace(tzinfo=None)
            if ws <= start and end <= we:
                fitting.append({**slot, "end_time": end.strftime("%H:%M")})
                break
    if result.availability_checked:
        result.fits = {"status": "fits" if fitting else "no_fitting_slot", "slots": fitting[:6]}
    else:
        result.fits = {"status": "availability_unknown", "free_windows": windows_by_day}
    point = _hotel_point(trip)
    if point and result.lat is not None:
        result.distance_km = round(geo.haversine_km(point[0], point[1], result.lat, result.lon), 1)


def search(user: User, req: ActivitySearchRequest, *, trip: Trip | None = None,
           providers: list[str] | None = None) -> dict:
    if trip and not req.location and trip.primary_destination:
        req.location = trip.primary_destination
    if trip and req.lat is None and trip.destinations:
        req.lat, req.lon = trip.destinations[0].lat, trip.destinations[0].lon
    if req.lat is None and req.location:
        place = geo.resolve_place(req.location)
        if place:
            req.lat, req.lon = place.lat, place.lon
    results: list[ActivityResult] = []
    statuses = []
    for adapter in adapters_for(user):
        caps = adapter.capabilities()
        if providers and adapter.key not in providers:
            continue
        status = {"provider": adapter.key, "name": adapter.name, "state": caps["state"], "count": 0, "error": None}
        if not caps["search"]:
            status["error"] = "Not available: " + caps["state"].replace("_", " ")
            statuses.append(status)
            continue
        try:
            found = adapter.search(req)
            status["count"] = len(found)
            results.extend(found)
        except (ProviderRequestError, ProviderCapabilityError) as exc:
            status["error"] = str(exc)
        statuses.append(status)
    if trip:
        days = []
        if req.date_from:
            d = req.date_from
            while d <= (req.date_to or req.date_from) and len(days) < 7:
                days.append(d)
                d += timedelta(days=1)
        for r in results:
            if days:
                analyse_fit(r, trip, days)
            else:
                point = _hotel_point(trip)
                if point and r.lat is not None:
                    r.distance_km = round(geo.haversine_km(point[0], point[1], r.lat, r.lon), 1)
    if req.start_after or req.end_before:
        results = [r for r in results if _within_time(r, req)]
    rank = {"fits": 0, "availability_unknown": 1, "no_fitting_slot": 2}
    # on a wet day outdoor options go last, and both the app and the assistant see why
    forecast = _day_weather(trip, req.date_from) if trip and req.date_from else None
    notes = {id(r): weather_note(r.title, r.categories, forecast) for r in results}
    results.sort(key=lambda r: (notes[id(r)] == "outdoor_in_bad_weather", rank.get(r.fits.get("status"), 1),
                                r.distance_km if r.distance_km is not None else 999))
    return {"results": [{**r.to_dict(), "weather_note": notes[id(r)]} for r in results[: req.limit]],
            "providers": statuses, "weather": forecast}


OUTDOOR_WORDS = ("outdoor", "park", "garden", "walk", "tour", "day trip", "viewpoint", "beach", "hike", "bike", "boat")


def _day_weather(trip: Trip, day) -> dict | None:
    from app.services.context import weather

    result = weather.for_trip(trip, day)
    return result["days"][0] if result.get("days") else None


def weather_note(title: str, categories: list[str] | None, forecast: dict | None) -> str | None:
    """"outdoor_in_bad_weather" or "indoor_good_for_rain" on a wet day; nothing otherwise"""
    if not forecast or forecast.get("outdoor_ok", True):
        return None
    text = " ".join([title or "", *(categories or [])]).lower()
    return "outdoor_in_bad_weather" if any(w in text for w in OUTDOOR_WORDS) else "indoor_good_for_rain"


def _within_time(r: ActivityResult, req: ActivitySearchRequest) -> bool:
    if not r.available_slots:
        return True
    keep = []
    for s in r.available_slots:
        if req.start_after and s["time"] < req.start_after:
            continue
        if req.end_before and r.duration_minutes:
            end = (datetime.strptime(s["time"], "%H:%M") + timedelta(minutes=r.duration_minutes)).strftime("%H:%M")
            if end > req.end_before:
                continue
        keep.append(s)
    r.available_slots = keep
    if r.fits.get("slots"):
        r.fits["slots"] = [s for s in r.fits["slots"] if s in keep or any(
            k["date"] == s["date"] and k["time"] == s["time"] for k in keep)]
        if not r.fits["slots"]:
            r.fits["status"] = "no_fitting_slot"
    return bool(keep)
