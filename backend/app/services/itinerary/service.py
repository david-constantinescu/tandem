"""editarea evenimentelor din itinerariu, cu ore pe fusul local"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db
from app.models import ItineraryEvent, Trip, User
from app.models.trip import EVENT_STATUSES, EVENT_TYPES
from app.services import geo
from app.services.audit import audit
from app.utils.errors import Conflict, ValidationFailed
from app.utils.timeutil import is_valid_tz, localize

EDITABLE = {"title", "notes", "type", "status", "start_local", "end_local", "start_tz", "end_tz", "location_name",
            "address", "city", "lat", "lon", "all_day"}


def _parse_local(value: str, tz: str, label: str) -> datetime:
    try:
        naive = datetime.fromisoformat(str(value)[:16])
    except ValueError as exc:
        raise ValidationFailed(f"Invalid {label}", code="invalid_datetime") from exc
    if naive.tzinfo is not None:
        naive = naive.replace(tzinfo=None)
    aware, _ = localize(naive, tz)
    return aware


def _default_tz(trip: Trip, user: User) -> str:
    from app.services.providers.activities import trip_timezone

    tz = trip_timezone(trip)
    return tz if tz != "UTC" else (user.timezone or "UTC")


def create_event(user: User, trip: Trip, data: dict, *, source: str = "manual") -> ItineraryEvent:
    tz = data.get("start_tz") if is_valid_tz(data.get("start_tz")) else _default_tz(trip, user)
    if not data.get("start_local"):
        raise ValidationFailed("A start date/time is required", code="start_required")
    etype = data.get("type") or "custom"
    status = data.get("status") or ("suggested" if source == "assistant" else "unbooked")
    if etype not in EVENT_TYPES or status not in EVENT_STATUSES:
        raise ValidationFailed("Unknown event type or status", code="invalid_event")
    if status == "confirmed" and source != "manual":
        raise ValidationFailed("Only bookings with a provider confirmation can be marked confirmed",
                               code="confirmation_required")
    start = _parse_local(data["start_local"], tz, "start time")
    end_tz = data.get("end_tz") if is_valid_tz(data.get("end_tz")) else tz
    end = _parse_local(data["end_local"], end_tz, "end time") if data.get("end_local") else None
    if end and end < start:
        raise ValidationFailed("End must be after start", code="invalid_times")
    lat, lon, city = data.get("lat"), data.get("lon"), data.get("city")
    if lat is None and (data.get("address") or city):
        place = geo.resolve_place(data.get("address") or city, allow_network=True)
        if place:
            lat, lon, city = place.lat, place.lon, city or place.city
    event = ItineraryEvent(
        user_id=user.id, trip_id=trip.id, type=etype, status=status, title=(data.get("title") or "Event")[:300],
        notes=data.get("notes") or "", start_at=start, start_tz=tz, end_at=end, end_tz=end_tz if end else None,
        location_name=data.get("location_name"), address=data.get("address"), city=city or trip.primary_destination,
        lat=lat, lon=lon, source=source, details=data.get("details") or {},
    )
    db.session.add(event)
    db.session.flush()
    audit(user.id, "event.created", actor="assistant" if source == "assistant" else "user", resource_type="event",
          resource_id=event.id, trip_id=str(trip.id))
    return event


def apply_event_changes(user: User, event: ItineraryEvent, changes: dict, *, allow_confirmed: bool = False,
                        actor: str = "user") -> ItineraryEvent:
    unknown = set(changes) - EDITABLE
    if unknown:
        raise ValidationFailed(f"Fields cannot be edited: {', '.join(sorted(unknown))}", code="invalid_fields")
    if event.reservation_id and set(changes) & {"start_local", "end_local", "start_tz", "end_tz"} and not allow_confirmed:
        raise Conflict("Times of booked reservations change only through the reservation or a provider update",
                       code="reservation_owned")
    if event.status == "confirmed" and not allow_confirmed and actor != "user":
        raise Conflict("Confirmed plans can only be changed after you approve a proposal", code="approval_required")
    if "status" in changes and changes["status"] not in EVENT_STATUSES:
        raise ValidationFailed("Unknown status", code="invalid_status")
    if changes.get("status") == "confirmed" and not event.reservation_id and actor != "user":
        raise ValidationFailed("Only the user can mark a non-booked event as confirmed", code="confirmation_required")
    tz = changes.get("start_tz") if is_valid_tz(changes.get("start_tz")) else event.start_tz
    end_tz = changes.get("end_tz") if is_valid_tz(changes.get("end_tz")) else (event.end_tz or tz)
    for key, value in changes.items():
        if key == "start_local":
            event.start_at = _parse_local(value, tz, "start time")
        elif key == "end_local":
            event.end_at = _parse_local(value, end_tz, "end time") if value else None
        elif key not in ("start_tz", "end_tz"):
            setattr(event, key, value)
    event.start_tz = tz
    event.end_tz = end_tz if event.end_at else None
    if event.end_at and event.end_at < event.start_at:
        raise ValidationFailed("End must be after start", code="invalid_times")
    audit(user.id, "event.updated", actor=actor, resource_type="event", resource_id=event.id, fields=sorted(changes))
    return event


def delete_event(user: User, event: ItineraryEvent, *, actor: str = "user") -> None:
    if event.reservation_id:
        raise Conflict("This event belongs to a reservation; remove or cancel the reservation instead",
                       code="reservation_owned")
    audit(user.id, "event.deleted", actor=actor, resource_type="event", resource_id=event.id)
    db.session.delete(event)
