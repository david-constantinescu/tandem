from __future__ import annotations

from flask import Blueprint, request
from pydantic import BaseModel, Field

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_body, parse_uuid
from app.extensions import db
from app.models import Reservation, ReservationChange, Trip
from app.models.trip import RESERVATION_STATUSES, RESERVATION_TYPES
from app.schemas.serializers import change_dict, reservation_dict
from app.services.audit import audit
from app.services.itinerary.conflicts import check_and_notify
from app.services.trips import service as trips
from app.utils.errors import NotFound, ValidationFailed

bp = Blueprint("reservations", __name__, url_prefix="/api/v1/reservations")


class ReservationBody(BaseModel):
    type: str
    title: str = Field(min_length=1, max_length=300)
    status: str = "confirmed"
    trip_id: str | None = None
    provider_name: str | None = None
    booking_reference: str | None = Field(default=None, max_length=64)
    start_local: str | None = Field(default=None, description="YYYY-MM-DDTHH:MM local")
    start_tz: str | None = None
    end_local: str | None = None
    end_tz: str | None = None
    origin: str | None = None
    destination: str | None = None
    location_name: str | None = None
    address: str | None = None
    city: str | None = None
    price: float | None = None
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    cancellation_policy: str | None = None
    details: dict = Field(default_factory=dict)


class ReservationPatch(BaseModel):
    title: str | None = None
    status: str | None = None
    provider_name: str | None = None
    booking_reference: str | None = None
    start_local: str | None = None
    start_tz: str | None = None
    end_local: str | None = None
    end_tz: str | None = None
    location_name: str | None = None
    address: str | None = None
    city: str | None = None
    price: float | None = None
    currency: str | None = None
    cancellation_policy: str | None = None
    details: dict | None = None


class MoveBody(BaseModel):
    trip_id: str | None = None


def _trip_or_none(trip_id: str | None) -> Trip | None:
    if not trip_id:
        return None
    t = db.session.get(Trip, parse_uuid(trip_id, "trip"))
    if t is None or t.user_id != current_user().id:
        raise NotFound("Trip not found")
    return t


def _after_change(res: Reservation) -> None:
    trips.sync_events(res)
    if res.trip_id:
        trip = db.session.get(Trip, res.trip_id)
        trips.refresh_trip(trip, current_user())
        db.session.flush()
        check_and_notify(trip, current_user())


@bp.get("")
@login_required
@doc("List reservations (filter: trip_id, unassigned=true)", tag="Reservations")
def list_reservations():
    u = current_user()
    q = db.select(Reservation).where(Reservation.user_id == u.id)
    if request.args.get("trip_id"):
        q = q.where(Reservation.trip_id == parse_uuid(request.args["trip_id"], "trip"))
    if request.args.get("unassigned") == "true":
        q = q.where(Reservation.trip_id.is_(None))
    rows = db.session.execute(q.order_by(Reservation.start_at)).scalars().all()
    return ok([reservation_dict(r) for r in rows])


@bp.post("")
@login_required
@doc("Add a reservation manually", body=ReservationBody, tag="Reservations")
def create_reservation():
    body = parse_body(ReservationBody)
    u = current_user()
    if body.type not in RESERVATION_TYPES or body.status not in RESERVATION_STATUSES:
        raise ValidationFailed("Unknown reservation type or status", code="invalid_reservation")
    trip = _trip_or_none(body.trip_id)
    data = trips.apply_corrections(u, {"type": body.type, "details": body.details}, {
        k: v for k, v in body.model_dump(exclude={"trip_id", "details"}).items() if v is not None})
    res = trips.reservation_from_data(u, data, trip=trip, verification="user_confirmed", created_via="manual")
    audit(u.id, "reservation.created", resource_type="reservation", resource_id=res.id)
    _after_change(res)
    db.session.commit()
    return ok(reservation_dict(res), 201)


@bp.get("/<res_id>")
@login_required
@doc("Reservation detail with change history", tag="Reservations")
def get_reservation(res_id):
    r = get_owned(Reservation, res_id, "reservation")
    changes = db.session.execute(db.select(ReservationChange).where(ReservationChange.reservation_id == r.id)
                                 .order_by(ReservationChange.detected_at.desc())).scalars().all()
    return ok({**reservation_dict(r), "changes": [change_dict(c) for c in changes]})


@bp.patch("/<res_id>")
@login_required
@doc("Edit a reservation", body=ReservationPatch, tag="Reservations")
def update_reservation(res_id):
    r = get_owned(Reservation, res_id, "reservation")
    body = parse_body(ReservationPatch)
    u = current_user()
    fields = body.model_dump(exclude_unset=True)
    if "status" in fields and fields["status"] not in RESERVATION_STATUSES:
        raise ValidationFailed("Unknown status", code="invalid_status")
    time_fields = {k: fields.pop(k) for k in ("start_local", "end_local", "start_tz", "end_tz") if k in fields}
    if time_fields:
        from app.utils.timeutil import iso_local

        current = {"start_local": (iso_local(r.start_at, r.start_tz) or "")[:16] or None, "start_tz": r.start_tz,
                   "end_local": (iso_local(r.end_at, r.end_tz or r.start_tz) or "")[:16] or None,
                   "end_tz": r.end_tz or r.start_tz}
        data = trips.apply_corrections(u, current, time_fields)
        from app.utils.timeutil import parse_iso_datetime

        r.start_at, r.start_tz = parse_iso_datetime(data.get("start_at")), data.get("start_tz")
        r.end_at, r.end_tz = parse_iso_datetime(data.get("end_at")), data.get("end_tz")
        if r.start_at and r.end_at and r.end_at < r.start_at:
            raise ValidationFailed("End must be after start", code="invalid_times")
    for key, value in fields.items():
        if key == "details":
            r.details = {**(r.details or {}), **(value or {})}
        elif key == "price":
            r.price = trips._decimal(value)
        else:
            setattr(r, key, value)
    r.verification = "user_confirmed"
    audit(u.id, "reservation.updated", resource_type="reservation", resource_id=r.id,
          fields=sorted(list(fields) + list(time_fields)))
    _after_change(r)
    db.session.commit()
    return ok(reservation_dict(r))


@bp.delete("/<res_id>")
@login_required
@doc("Delete a reservation from Tandem (does not cancel it with the provider)", tag="Reservations")
def delete_reservation(res_id):
    r = get_owned(Reservation, res_id, "reservation")
    u = current_user()
    trip = db.session.get(Trip, r.trip_id) if r.trip_id else None
    audit(u.id, "reservation.deleted", resource_type="reservation", resource_id=r.id)
    db.session.delete(r)
    db.session.flush()
    if trip:
        trips.refresh_trip(trip, u)
        check_and_notify(trip, u)
    db.session.commit()
    return ok({"deleted": True, "note": "Removed from Tandem only. The booking with the provider is unchanged."})


@bp.post("/<res_id>/move")
@login_required
@doc("Move a reservation to another trip (or unassign)", body=MoveBody, tag="Reservations")
def move_reservation(res_id):
    r = get_owned(Reservation, res_id, "reservation")
    body = parse_body(MoveBody)
    trips.move_reservation(current_user(), r, _trip_or_none(body.trip_id))
    db.session.commit()
    return ok(reservation_dict(r))


@bp.get("/<res_id>/changes")
@login_required
@doc("Change history for a reservation", tag="Reservations")
def reservation_changes(res_id):
    r = get_owned(Reservation, res_id, "reservation")
    rows = db.session.execute(db.select(ReservationChange).where(ReservationChange.reservation_id == r.id)
                              .order_by(ReservationChange.detected_at.desc())).scalars().all()
    return ok([change_dict(c) for c in rows])


@bp.post("/changes/<change_id>/apply")
@login_required
@doc("Apply a detected reservation change", tag="Reservations")
def apply_change(change_id):
    c = get_owned(ReservationChange, change_id, "change")
    res = trips.apply_change(current_user(), c)
    db.session.commit()
    return ok({"change": change_dict(c), "reservation": reservation_dict(res)})


@bp.post("/changes/<change_id>/dismiss")
@login_required
@doc("Dismiss a detected reservation change", tag="Reservations")
def dismiss_change(change_id):
    c = get_owned(ReservationChange, change_id, "change")
    trips.dismiss_change(current_user(), c)
    db.session.commit()
    return ok(change_dict(c))
