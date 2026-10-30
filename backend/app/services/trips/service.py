"""Trips and reservations: turning reviewed records into reservations, itinerary sync, change handling."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import (
    Document, ExtractedRecord, ItineraryEvent, Reservation, ReservationChange, Traveller, Trip, TripDestination, User,
)
from app.models.trip import RESERVATION_TYPES
from app.services import geo
from app.services.audit import audit
from app.services.notifications.service import notify
from app.services.trips import grouping
from app.utils.errors import Conflict, ValidationFailed
from app.utils.timeutil import is_valid_tz, local_date, parse_iso_datetime, utcnow

TRANSPORT = {"flight", "train", "bus", "ferry", "transfer"}
EVENT_TYPE_FOR = {
    "activity": "activity", "tour": "tour", "museum": "museum", "restaurant": "restaurant", "event": "event",
    "other": "custom", "transfer": "transfer",
}
STATUS_FOR_EVENT = {"confirmed": "confirmed", "pending": "pending", "unknown": "pending", "cancelled": "cancelled"}
CHANGE_FIELDS = ("start_at", "end_at", "start_tz", "end_tz", "status", "address", "location_name", "price",
                 "currency", "origin", "destination", "cancellation_deadline")
CHANGE_DETAIL_FIELDS = ("terminal", "gate", "seat", "flight_number", "meeting_point", "room_type", "party_size",
                        "check_in_from", "check_out_until")


def _squash(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _decimal(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------------------------------------------------
# Trips
def create_trip(user: User, name: str, *, start_date: date | None = None, end_date: date | None = None,
                destination: str | None = None, created_via: str = "user", grouping_info: dict | None = None,
                lat: float | None = None, lon: float | None = None) -> Trip:
    trip = Trip(user_id=user.id, name=name.strip()[:200] or "New trip", start_date=start_date, end_date=end_date,
                primary_destination=destination, created_via=created_via, grouping=grouping_info or {})
    db.session.add(trip)
    db.session.flush()
    if destination:
        add_destination(trip, destination, lat=lat, lon=lon, arrive=start_date, depart=end_date)
    if user.display_name:
        db.session.add(Traveller(trip_id=trip.id, full_name=user.display_name, is_primary=True))
    return trip


def add_destination(trip: Trip, name: str, *, lat=None, lon=None, arrive=None, depart=None,
                    allow_network: bool = False) -> TripDestination:
    existing = next((d for d in trip.destinations if _squash(d.name) == _squash(name)), None)
    if existing:
        existing.arrive_date = existing.arrive_date or arrive
        existing.depart_date = max(filter(None, [existing.depart_date, depart]), default=None)
        return existing
    place = geo.resolve_place(name, allow_network=allow_network) if lat is None else None
    lat = lat if lat is not None else (place.lat if place else None)
    lon = lon if lon is not None else (place.lon if place else None)
    dest = TripDestination(trip_id=trip.id, name=name[:200], lat=lat, lon=lon,
                           country=place.country if place else None,
                           timezone=(place.tz if place else None) or geo.tz_for_point(lat, lon),
                           arrive_date=arrive, depart_date=depart, position=len(trip.destinations))
    trip.destinations.append(dest)
    return dest


def refresh_trip(trip: Trip, user: User) -> None:
    """Recompute trip date bounds and destinations from its reservations and events."""
    events = db.session.execute(db.select(ItineraryEvent).where(
        ItineraryEvent.trip_id == trip.id, ItineraryEvent.status != "cancelled")).scalars().all()
    dates = []
    for e in events:
        dates.append(local_date(e.start_at, e.start_tz))
        if e.end_at:
            dates.append(local_date(e.end_at, e.end_tz or e.start_tz))
    if dates:
        trip.start_date = min(dates + ([trip.start_date] if trip.start_date and trip.created_via == "user" else []))
        trip.end_date = max(dates + ([trip.end_date] if trip.end_date and trip.created_via == "user" else []))
    home = _squash(user.home_city)
    reservations = db.session.execute(db.select(Reservation).where(
        Reservation.trip_id == trip.id, Reservation.status != "cancelled").order_by(Reservation.start_at)).scalars().all()
    # Where the trip starts from (the first journey's departure city) is home, not a destination.
    first_transport = next((r for r in reservations if r.type in TRANSPORT and r.city), None)
    origin = _squash(first_transport.city) if first_transport else ""
    for r in reservations:
        if r.type in ("flight", "train", "bus", "ferry"):
            city = (r.details or {}).get("arrival_city")
        else:
            city = r.city
        if city and _squash(city) not in {home, origin}:
            arrive = local_date(r.start_at, r.start_tz) if r.start_at else None
            add_destination(trip, city, lat=r.lat if r.type not in TRANSPORT else None,
                            lon=r.lon if r.type not in TRANSPORT else None, arrive=arrive,
                            depart=local_date(r.end_at, r.end_tz or r.start_tz) if r.end_at else arrive)
    if not trip.primary_destination and trip.destinations:
        trip.primary_destination = trip.destinations[0].name


# ---------------------------------------------------------------------------------------
# Reservations
def reservation_from_data(user: User, data: dict, *, trip: Trip | None, source_document_id=None,
                          confidence: float | None = None, verification: str = "user_confirmed",
                          created_via: str = "extraction") -> Reservation:
    rtype = data.get("type") if data.get("type") in RESERVATION_TYPES else "other"
    details = dict(data.get("details") or {})
    if rtype in TRANSPORT:
        details.setdefault("arrival_city", data.get("end_city"))
        details.setdefault("arrival_lat", data.get("end_lat"))
        details.setdefault("arrival_lon", data.get("end_lon"))
        details.setdefault("origin_code", data.get("origin_code"))
        details.setdefault("destination_code", data.get("destination_code"))
    res = Reservation(
        user_id=user.id, trip_id=trip.id if trip else None, type=rtype,
        status=data.get("status") if data.get("status") in ("confirmed", "pending", "cancelled") else "unknown",
        title=(data.get("title") or rtype.title())[:300], provider_name=data.get("provider_name"),
        booking_reference=(data.get("booking_reference") or None), description=data.get("description"),
        origin=data.get("origin"), destination=data.get("destination"),
        start_at=parse_iso_datetime(data.get("start_at")), start_tz=_tz(data.get("start_tz"), user),
        end_at=parse_iso_datetime(data.get("end_at")), end_tz=_tz(data.get("end_tz"), user),
        location_name=data.get("location_name"), address=data.get("address"), city=data.get("city"),
        lat=data.get("lat"), lon=data.get("lon"), price=_decimal(data.get("price")), currency=data.get("currency"),
        travellers=data.get("travellers") or [], details={k: v for k, v in details.items() if v is not None},
        cancellation_deadline=parse_iso_datetime(data.get("cancellation_deadline")),
        cancellation_policy=data.get("cancellation_policy"), website=data.get("website"), contact=data.get("contact"),
        source_document_id=source_document_id, confidence=confidence, verification=verification,
        created_via=created_via,
    )
    if res.start_at and res.end_at and res.end_at < res.start_at:
        raise ValidationFailed("End time is before start time", code="invalid_times")
    db.session.add(res)
    db.session.flush()
    return res


def _tz(name: str | None, user: User) -> str:
    return name if is_valid_tz(name) else (user.timezone or "UTC")


def sync_events(res: Reservation) -> list[ItineraryEvent]:
    """Create or update the itinerary events that represent a reservation."""
    if res.trip_id is None:
        for e in db.session.execute(db.select(ItineraryEvent).where(ItineraryEvent.reservation_id == res.id)).scalars():
            db.session.delete(e)
        return []
    existing = {(e.details or {}).get("role", "main"): e for e in db.session.execute(
        db.select(ItineraryEvent).where(ItineraryEvent.reservation_id == res.id)).scalars()}
    status = STATUS_FOR_EVENT.get(res.status, "pending")
    details = res.details or {}
    specs: list[dict] = []
    if res.start_at is None:
        specs = []
    elif res.type in TRANSPORT or res.type == "transfer":
        specs.append({"role": "main", "type": res.type, "title": res.title, "start_at": res.start_at,
                      "start_tz": res.start_tz, "end_at": res.end_at, "end_tz": res.end_tz or res.start_tz,
                      "location_name": res.origin, "city": res.city, "lat": res.lat, "lon": res.lon,
                      "end_location_name": res.destination, "end_city": details.get("arrival_city"),
                      "end_lat": details.get("arrival_lat"), "end_lon": details.get("arrival_lon")})
    elif res.type in ("hotel", "car_rental"):
        first, last = ("hotel_checkin", "hotel_checkout") if res.type == "hotel" else ("car_rental", "car_rental")
        name = res.provider_name or res.title
        labels = ("Check in", "Check out") if res.type == "hotel" else ("Pick up", "Drop off")
        common = {"location_name": res.location_name or name, "city": res.city, "lat": res.lat, "lon": res.lon}
        specs.append({"role": "start", "type": first, "title": f"{labels[0]} · {name}", "start_at": res.start_at,
                      "start_tz": res.start_tz, "end_at": None, "end_tz": None, **common})
        if res.end_at:
            specs.append({"role": "end", "type": last, "title": f"{labels[1]} · {name}", "start_at": res.end_at,
                          "start_tz": res.end_tz or res.start_tz, "end_at": None, "end_tz": None, **common})
    else:
        specs.append({"role": "main", "type": EVENT_TYPE_FOR.get(res.type, "custom"), "title": res.title,
                      "start_at": res.start_at, "start_tz": res.start_tz, "end_at": res.end_at,
                      "end_tz": res.end_tz or res.start_tz, "location_name": res.location_name,
                      "city": res.city, "lat": res.lat, "lon": res.lon})
    events = []
    for spec in specs:
        role = spec.pop("role")
        event = existing.pop(role, None)
        if event is None:
            event = ItineraryEvent(user_id=res.user_id, trip_id=res.trip_id, reservation_id=res.id, source="reservation")
            db.session.add(event)
        for key, value in spec.items():
            setattr(event, key, value)
        event.trip_id = res.trip_id
        event.address = res.address
        # Preserve user-marked completion but follow reservation status otherwise.
        if not (event.status == "completed" and status == "confirmed"):
            event.status = status
        event.details = {**(event.details or {}), "role": role, "reservation_type": res.type,
                         "booking_reference": res.booking_reference}
        events.append(event)
    for stale in existing.values():
        db.session.delete(stale)
    db.session.flush()
    return events


def assign_trip_for_data(user: User, data: dict, choice: dict | None) -> tuple[Trip | None, dict]:
    """Resolve the trip a record goes into: explicit choice, else a fresh grouping proposal."""
    choice = choice or {}
    if choice.get("trip_id"):
        trip = db.session.get(Trip, choice["trip_id"])
        if trip is None or trip.user_id != user.id:
            raise ValidationFailed("Trip not found", code="trip_not_found")
        return trip, {"action": "join", "trip_id": str(trip.id), "chosen_by": "user"}
    if choice.get("no_trip"):
        return None, {"action": "none", "chosen_by": "user"}
    proposal = grouping.propose(user, data)
    if choice.get("new_trip") or proposal["action"] == "create":
        spec = {**(proposal.get("new_trip") or {}), **(choice.get("new_trip") or {})}
        trip = create_trip(
            user, spec.get("name") or "New trip",
            start_date=date.fromisoformat(spec["start_date"]) if spec.get("start_date") else None,
            end_date=date.fromisoformat(spec["end_date"]) if spec.get("end_date") else None,
            destination=spec.get("destination"), created_via="auto",
            grouping_info={"created_from": "extraction", "reasons": proposal.get("reasons", [])},
            lat=spec.get("lat"), lon=spec.get("lon"),
        )
        notify(user.id, "trip_created", f"New trip: {trip.name}",
               "Created from a document in your inbox. You can rename it or move records to another trip.",
               link=f"/trips/{trip.id}", dedupe_key=f"trip_created:{trip.id}")
        return trip, {**proposal, "trip_id": str(trip.id)}
    trip = db.session.get(Trip, proposal["trip_id"])
    return trip, proposal


def accept_record(user: User, record: ExtractedRecord, *, corrections: dict | None = None,
                  trip_choice: dict | None = None, actor: str = "user") -> Reservation:
    if record.status not in ("pending_review",):
        raise Conflict(f"This record is already {record.status.replace('_', ' ')}", code="record_not_pending")
    data = dict(record.data)
    corrections = corrections or {}
    if corrections:
        data = apply_corrections(user, data, corrections)
        for f in record.fields:
            if f.field_name in corrections:
                f.verification = "user_corrected"
                f.value = corrections[f.field_name]
    unverified = any(f.verification == "not_found_in_source" for f in record.fields if f.field_name not in corrections)
    if actor != "user" and unverified:
        raise Conflict("Records with unverified fields need a manual review", code="needs_review")
    if actor == "user":
        # The user reviewed the record (including any highlighted warnings) and accepted it.
        for f in record.fields:
            if f.field_name not in corrections:
                f.verification = "user_confirmed"
    trip, decision = assign_trip_for_data(user, data, trip_choice)
    res = reservation_from_data(
        user, data, trip=trip, source_document_id=record.document_id, confidence=record.confidence,
        verification="user_confirmed" if actor == "user" else "verified",
    )
    sync_events(res)
    record.status = "accepted"
    record.reservation_id = res.id
    record.reviewed_at = utcnow()
    record.grouping = {**(record.grouping or {}), "applied": decision}
    doc = db.session.get(Document, record.document_id)
    if doc and trip and doc.trip_id is None:
        doc.trip_id = trip.id
    if trip:
        refresh_trip(trip, user)
    _finish_document_if_reviewed(doc)
    audit(user.id, "record.accepted", actor=actor, resource_type="reservation", resource_id=res.id,
          trip_id=str(trip.id) if trip else None, corrected_fields=sorted(corrections))
    db.session.flush()
    refresh_pending_proposals(user, exclude_id=record.id)
    if trip:
        from app.services.itinerary.conflicts import check_and_notify

        check_and_notify(trip, user)
    return res


def refresh_pending_proposals(user: User, exclude_id=None, limit: int = 50) -> None:
    """Re-run grouping for records still awaiting review, so proposals reflect trips created since analysis
    (e.g. the hotel uploaded together with the flight now proposes joining the flight's new trip)."""
    import uuid as _uuid

    pending = db.session.execute(db.select(ExtractedRecord).where(
        ExtractedRecord.user_id == user.id, ExtractedRecord.status == "pending_review",
        ExtractedRecord.id != exclude_id).limit(limit)).scalars().all()
    for rec in pending:
        proposal = grouping.propose(user, rec.data)
        rec.grouping = proposal
        rec.proposed_trip_id = _uuid.UUID(proposal["trip_id"]) if proposal.get("trip_id") else None


def reject_record(user: User, record: ExtractedRecord) -> None:
    record.status = "rejected"
    record.reviewed_at = utcnow()
    _finish_document_if_reviewed(db.session.get(Document, record.document_id))
    audit(user.id, "record.rejected", resource_type="extracted_record", resource_id=record.id)


def _finish_document_if_reviewed(doc: Document | None) -> None:
    if doc is None:
        return
    if all(r.status not in ("pending_review", "change_detected") for r in doc.records):
        doc.status = "processed"


def apply_corrections(user: User, data: dict, corrections: dict) -> dict:
    """Merge user corrections into normalised data, recomputing UTC instants when local times change."""
    from app.utils.timeutil import iso, localize
    from datetime import datetime

    data = {**data, "details": dict(data.get("details") or {})}
    detail_keys = set(CHANGE_DETAIL_FIELDS) | {"airline", "baggage", "ticket_number", "cabin_class", "guests",
                                               "nights", "train_number", "carriage", "operator"}
    for key, value in corrections.items():
        if key in detail_keys:
            data["details"][key] = value
        else:
            data[key] = value
    for local_key, tz_key, utc_key in (("start_local", "start_tz", "start_at"), ("end_local", "end_tz", "end_at")):
        if local_key in corrections or tz_key in corrections:
            local = data.get(local_key)
            if not local:
                data[utc_key] = None
                continue
            tz = data.get(tz_key) if is_valid_tz(data.get(tz_key)) else (user.timezone or "UTC")
            try:
                naive = datetime.fromisoformat(str(local)[:16])
            except ValueError as exc:
                raise ValidationFailed(f"Invalid date/time for {local_key}", code="invalid_datetime") from exc
            aware, _ = localize(naive, tz)
            data[tz_key] = tz
            data[utc_key] = iso(aware)
    if "city" in corrections and corrections["city"]:
        place = geo.resolve_place(corrections["city"], allow_network=False)
        if place:
            data["lat"], data["lon"] = place.lat, place.lon
    return data


# ---------------------------------------------------------------------------------------
# Change detection
def find_matching_reservation(user: User, data: dict) -> Reservation | None:
    ref = _squash(data.get("booking_reference"))
    if not ref:
        return None
    candidates = db.session.execute(db.select(Reservation).where(
        Reservation.user_id == user.id, Reservation.booking_reference.is_not(None))).scalars().all()
    matches = [r for r in candidates if _squash(r.booking_reference) == ref and r.type == data.get("type")]
    if data.get("type") == "flight" and len(matches) > 1:
        fn = _squash((data.get("details") or {}).get("flight_number"))
        matches = [r for r in matches if _squash((r.details or {}).get("flight_number")) == fn] or matches
    return matches[0] if len(matches) == 1 else (matches[0] if matches else None)


def relocalize(data: dict, start_tz: str | None, end_tz: str | None) -> dict:
    """Re-read local wall-clock times in the given zones (used when a document's zone was only assumed)."""
    from datetime import datetime

    from app.utils.timeutil import iso, localize

    out = dict(data)
    for local_key, tz_key, utc_key, flag, tz in (("start_local", "start_tz", "start_at", "start_tz_assumed", start_tz),
                                                  ("end_local", "end_tz", "end_at", "end_tz_assumed", end_tz)):
        if out.get(flag) and tz and out.get(local_key):
            aware, _ = localize(datetime.fromisoformat(str(out[local_key])[:16]), tz)
            out[tz_key], out[utc_key], out[flag] = tz, iso(aware), False
    return out


def diff_reservation(res: Reservation, data: dict) -> dict:
    changes: dict = {}
    new = {
        "start_at": parse_iso_datetime(data.get("start_at")), "end_at": parse_iso_datetime(data.get("end_at")),
        "start_tz": data.get("start_tz"), "end_tz": data.get("end_tz"), "status": data.get("status"),
        "address": data.get("address"), "location_name": data.get("location_name"),
        "price": _decimal(data.get("price")), "currency": data.get("currency"), "origin": data.get("origin"),
        "destination": data.get("destination"),
        "cancellation_deadline": parse_iso_datetime(data.get("cancellation_deadline")),
    }
    for key in CHANGE_FIELDS:
        old_v, new_v = getattr(res, key), new.get(key)
        if new_v in (None, "", "unknown"):
            continue  # a missing value in an update is not treated as a removal
        if old_v != new_v:
            changes[key] = {"old": _jsonable(old_v), "new": _jsonable(new_v)}
    new_details = data.get("details") or {}
    for key in CHANGE_DETAIL_FIELDS:
        old_v, new_v = (res.details or {}).get(key), new_details.get(key)
        if new_v not in (None, "") and old_v != new_v:
            changes[f"details.{key}"] = {"old": old_v, "new": new_v}
    return changes


def _jsonable(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def summarise_changes(res: Reservation, changes: dict) -> str:
    labels = {"start_at": "start time", "end_at": "end time", "status": "status", "address": "address",
              "location_name": "location", "price": "price", "details.gate": "gate", "details.terminal": "terminal",
              "details.seat": "seat", "details.meeting_point": "meeting point", "cancellation_deadline":
              "cancellation deadline"}
    parts = [labels.get(k, k.replace("details.", "").replace("_", " ")) for k in changes]
    return f"{res.title}: {', '.join(parts)} changed" if parts else f"{res.title}: no changes"


def record_change(user: User, res: Reservation, record: ExtractedRecord, changes: dict) -> ReservationChange:
    change = ReservationChange(reservation_id=res.id, user_id=user.id, source_document_id=record.document_id,
                               extracted_record_id=record.id, changes=changes, summary=summarise_changes(res, changes))
    db.session.add(change)
    db.session.flush()
    notify(user.id, "reservation_changed", "Reservation update detected", change.summary,
           link=f"/inbox/{record.document_id}", severity="warning", dedupe_key=f"change:{change.id}")
    return change


def apply_change(user: User, change: ReservationChange, *, actor: str = "user") -> Reservation:
    if change.status != "pending":
        raise Conflict("This change was already resolved", code="change_resolved")
    res = db.session.get(Reservation, change.reservation_id)
    for key, diff in change.changes.items():
        value = diff["new"]
        if key.startswith("details."):
            res.details = {**(res.details or {}), key.split(".", 1)[1]: value}
        elif key in ("start_at", "end_at", "cancellation_deadline"):
            setattr(res, key, parse_iso_datetime(value))
        elif key == "price":
            res.price = _decimal(value)
        else:
            setattr(res, key, value)
    res.details = {**(res.details or {}), "history": (res.details or {}).get("history", []) + [
        {"change_id": str(change.id), "applied_at": utcnow().isoformat(), "changes": change.changes}]}
    change.status = "applied"
    change.resolved_at = utcnow()
    if change.extracted_record_id:
        rec = db.session.get(ExtractedRecord, change.extracted_record_id)
        if rec:
            rec.status = "accepted"
            rec.reservation_id = res.id
            rec.reviewed_at = utcnow()
            _finish_document_if_reviewed(db.session.get(Document, rec.document_id))
    sync_events(res)
    audit(user.id, "reservation.change_applied", actor=actor, resource_type="reservation", resource_id=res.id,
          fields=sorted(change.changes))
    if res.trip_id:
        trip = db.session.get(Trip, res.trip_id)
        refresh_trip(trip, user)
        db.session.flush()
        from app.services.itinerary.conflicts import check_and_notify

        check_and_notify(trip, user)
    return res


def dismiss_change(user: User, change: ReservationChange) -> None:
    if change.status != "pending":
        raise Conflict("This change was already resolved", code="change_resolved")
    change.status = "dismissed"
    change.resolved_at = utcnow()
    if change.extracted_record_id:
        rec = db.session.get(ExtractedRecord, change.extracted_record_id)
        if rec:
            rec.status = "rejected"
            rec.reviewed_at = utcnow()
            _finish_document_if_reviewed(db.session.get(Document, rec.document_id))
    audit(user.id, "reservation.change_dismissed", resource_type="reservation", resource_id=change.reservation_id)


def move_reservation(user: User, res: Reservation, trip: Trip | None) -> None:
    old_trip = db.session.get(Trip, res.trip_id) if res.trip_id else None
    res.trip_id = trip.id if trip else None
    sync_events(res)
    for t in filter(None, (old_trip, trip)):
        refresh_trip(t, user)
    audit(user.id, "reservation.moved", resource_type="reservation", resource_id=res.id,
          from_trip=str(old_trip.id) if old_trip else None, to_trip=str(trip.id) if trip else None)
