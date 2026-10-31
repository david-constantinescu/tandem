"""un rezumat scurt cu tot ce stim despre om si calatorie, merge in promptul asistentului la fiecare mesaj"""
from __future__ import annotations

import logging

from app.extensions import db
from app.models import AgentAction, ItineraryEvent, Reservation, Trip, User
from app.services.itinerary import conflicts as conflict_engine
from app.utils.timeutil import iso_local, local_date

log = logging.getLogger("tandem.agent")

MAX_CHARS = 5200


def _line(e: ItineraryEvent) -> str:
    start = iso_local(e.start_at, e.start_tz)[11:16]
    end = iso_local(e.end_at, e.end_tz or e.start_tz)[11:16] if e.end_at else ""
    flag = {"suggested": " (suggestion)", "unbooked": " (planned, not booked)", "cancelled": " (cancelled)"}.get(e.status, "")
    place = f" @ {e.location_name}" if e.location_name and e.location_name not in e.title else ""
    return f"  {start}{'-' + end if end else ''} {e.title}{place}{flag}"


def _weather_lines(trip: Trip) -> list[str]:
    from app.services.context import weather

    try:
        data = weather.for_trip(trip)
    except Exception:  # noqa: BLE001 - the brief must never break a conversation
        log.warning("brief: weather unavailable", exc_info=True)
        return []
    if not data.get("available"):
        return []
    return [f"  {d['date']}: {d['condition']}, {round(d['temp_min'])}-{round(d['temp_max'])}C, rain {d['precip_probability']}%"
            f"{'' if d['outdoor_ok'] else ' (better indoors)'}" for d in data["days"]
            if d["temp_max"] is not None and d["temp_min"] is not None]


def trip_brief(user: User, trip: Trip | None) -> str:
    """plain text, newest facts first, capped so it never crowds out the conversation"""
    if trip is None:
        return "No trip is focused. Use list_trips to see the user's trips."
    out = [f"Trip: {trip.name} ({trip.start_date} to {trip.end_date}), destination {trip.primary_destination}.",
           f"Travellers: {', '.join(t.full_name for t in trip.travellers) or user.display_name or 'the user'}. "
           f"Travelling from {user.home_city or 'unknown'}."]
    reservations = db.session.execute(db.select(Reservation).where(Reservation.trip_id == trip.id)
                                      .order_by(Reservation.start_at)).scalars().all()
    if reservations:
        out.append("Bookings:")
        for r in reservations:
            start = iso_local(r.start_at, r.start_tz)[:16].replace("T", " ")
            ref = f", ref {r.booking_reference}" if r.booking_reference else ""
            out.append(f"  {r.type}: {r.title} — {r.status}{ref}, {start} {r.start_tz or ''}")
    events = db.session.execute(db.select(ItineraryEvent).where(
        ItineraryEvent.trip_id == trip.id, ItineraryEvent.status != "cancelled", ItineraryEvent.reservation_id.is_(None))
        .order_by(ItineraryEvent.start_at)).scalars().all()
    if events:
        out.append("Plan (not tied to a booking), local times:")
        day = None
        for e in events:
            d = local_date(e.start_at, e.start_tz)
            if d != day:
                day = d
                out.append(f" {d.isoformat()} {d.strftime('%A')}:")
            out.append(_line(e))
    try:
        clashes = conflict_engine.detect(trip)
    except Exception:  # noqa: BLE001
        clashes = []
    if clashes:
        from app.i18n import render

        out.append("Known clashes (background only: mention them only if the request is about the plan, timing or these events): "
                   + "; ".join(render(c.title) for c in clashes[:5]))
    pending = db.session.execute(db.select(db.func.count(AgentAction.id)).where(
        AgentAction.user_id == user.id, AgentAction.status == "awaiting_approval")).scalar() or 0
    if pending:
        out.append(f"Awaiting the user's approval: {pending} action(s).")
    weather_lines = _weather_lines(trip)
    if weather_lines:
        out.append("Forecast (Open-Meteo):")
        out.extend(weather_lines)
    prefs = user.preferences
    if prefs:
        out.append(f"Preferences: interests {', '.join(prefs.interests or []) or 'none stated'}; pace {prefs.pace}; "
                   f"budget {prefs.budget or 'unspecified'}; accessibility {prefs.accessibility_needs or 'none'}.")
    text = "\n".join(out)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n...(brief truncated; use the tools for more)"
