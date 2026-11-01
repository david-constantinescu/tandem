from __future__ import annotations

from datetime import date

from flask import Blueprint, request
from pydantic import BaseModel, Field

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_body, parse_uuid
from app.i18n import locale_of, render, tr
from app.extensions import db
from app.models import Document, ItineraryEvent, Reservation, ReservationChange, Traveller, Trip, User
from app.schemas.serializers import change_dict, document_dict, event_dict, reservation_dict, trip_dict
from app.services.ai.base import TASK_EXPLANATION, AIError, AIRequest, ChatMessage
from app.services.ai.router import AIRouter
from app.services.audit import audit
from app.services import sharing
from app.services.itinerary import conflicts as conflict_engine
from app.services.trips import service as trips
from app.utils.errors import NotFound, ValidationFailed
from app.utils.timeutil import utcnow

bp = Blueprint("trips", __name__, url_prefix="/api/v1/trips")


class TripBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    primary_destination: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=20000)


class TripPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    primary_destination: str | None = None
    notes: str | None = Field(default=None, max_length=20000)
    is_cancelled: bool | None = None


class DestinationBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    arrive_date: date | None = None
    depart_date: date | None = None


class TravellerBody(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)


def _stats(t: Trip) -> dict:
    n_res = db.session.execute(db.select(db.func.count(Reservation.id)).where(Reservation.trip_id == t.id)).scalar()
    n_docs = db.session.execute(db.select(db.func.count(Document.id)).where(Document.trip_id == t.id)).scalar()
    next_event = db.session.execute(db.select(ItineraryEvent).where(
        ItineraryEvent.trip_id == t.id, ItineraryEvent.start_at >= utcnow(),
        ItineraryEvent.status.in_(["confirmed", "pending"])).order_by(ItineraryEvent.start_at).limit(1)).scalar()
    today = utcnow().date()
    phase = "planning"
    if t.is_cancelled:
        phase = "cancelled"
    elif t.start_date and t.end_date:
        phase = "past" if t.end_date < today else "current" if t.start_date <= today else "upcoming"
    types = db.session.execute(db.select(Reservation.type, db.func.count(Reservation.id)).where(
        Reservation.trip_id == t.id).group_by(Reservation.type)).all()
    return {"reservations": n_res, "documents": n_docs, "phase": phase,
            "reservation_types": {k: v for k, v in types},
            "next_event": event_dict(next_event) if next_event else None,
            "conflict_count": len([k for k in (t.known_conflicts or []) if not k.startswith(("unconfirmed", "missing_"))])}


def viewable_trip(trip_id) -> tuple[Trip, str]:
    """calatoria mea sau una impartita cu mine; la fel ca get_owned, un id strain nu da de gol nimic"""
    t = db.session.get(Trip, parse_uuid(trip_id, "trip"))
    role = sharing.role_of(t, current_user()) if t else None
    if t is None or role is None:
        raise NotFound("Trip not found")
    return t, role


def _shown(t: Trip, role: str) -> dict:
    out = {**trip_dict(t, stats=_stats(t)), "role": role}
    if role != "owner":
        owner = db.session.get(User, t.user_id)
        out["owner_name"] = owner.display_name or owner.email.split("@")[0]
    return out


@bp.get("")
@login_required
@doc("List trips (mine and the ones shared with me)", tag="Trips")
def list_trips():
    u = current_user()
    shared = sharing.shared_trip_ids(u)
    rows = db.session.execute(db.select(Trip).where((Trip.user_id == u.id) | Trip.id.in_(shared or [None]))
                              .order_by(Trip.start_date.is_(None), Trip.start_date)).scalars().all()
    return ok([_shown(t, "owner" if t.user_id == u.id else "member") for t in rows])


@bp.post("")
@login_required
@doc("Create a trip", body=TripBody, tag="Trips")
def create_trip():
    body = parse_body(TripBody)
    if body.start_date and body.end_date and body.end_date < body.start_date:
        raise ValidationFailed("End date must be on or after the start date", code="invalid_dates")
    u = current_user()
    t = trips.create_trip(u, body.name, start_date=body.start_date, end_date=body.end_date,
                          destination=body.primary_destination)
    if body.notes:
        t.notes = body.notes
    audit(u.id, "trip.created", resource_type="trip", resource_id=t.id)
    db.session.commit()
    return ok(trip_dict(t, stats=_stats(t)), 201)


@bp.get("/<trip_id>")
@login_required
@doc("Trip detail", tag="Trips")
def get_trip(trip_id):
    t, role = viewable_trip(trip_id)
    return ok(_shown(t, role))


@bp.patch("/<trip_id>")
@login_required
@doc("Update a trip", body=TripPatch, tag="Trips")
def update_trip(trip_id):
    t = get_owned(Trip, trip_id, "trip")
    body = parse_body(TripPatch)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(t, key, value)
    if t.start_date and t.end_date and t.end_date < t.start_date:
        raise ValidationFailed("End date must be on or after the start date", code="invalid_dates")
    t.created_via = "user" if t.created_via == "auto" and ("start_date" in body.model_fields_set) else t.created_via
    db.session.commit()
    return ok(trip_dict(t, stats=_stats(t)))


@bp.delete("/<trip_id>")
@login_required
@doc("Delete a trip (reservations are kept and become unassigned unless delete_reservations=true)", tag="Trips")
def delete_trip(trip_id):
    t = get_owned(Trip, trip_id, "trip")
    u = current_user()
    delete_res = request.args.get("delete_reservations") == "true"
    for r in db.session.execute(db.select(Reservation).where(Reservation.trip_id == t.id)).scalars():
        if delete_res:
            db.session.delete(r)
        else:
            r.trip_id = None
    audit(u.id, "trip.deleted", resource_type="trip", resource_id=t.id, deleted_reservations=delete_res)
    db.session.delete(t)
    db.session.commit()
    return ok({"deleted": True})


@bp.post("/<trip_id>/destinations")
@login_required
@doc("Add a destination", body=DestinationBody, tag="Trips")
def add_destination(trip_id):
    t = get_owned(Trip, trip_id, "trip")
    body = parse_body(DestinationBody)
    trips.add_destination(t, body.name, arrive=body.arrive_date, depart=body.depart_date, allow_network=True)
    db.session.commit()
    return ok(trip_dict(t, stats=_stats(t)), 201)


@bp.delete("/<trip_id>/destinations/<dest_id>")
@login_required
@doc("Remove a destination", tag="Trips")
def remove_destination(trip_id, dest_id):
    t = get_owned(Trip, trip_id, "trip")
    d = next((d for d in t.destinations if str(d.id) == dest_id), None)
    if d:
        db.session.delete(d)
    db.session.commit()
    return ok(trip_dict(t, stats=_stats(t)))


@bp.post("/<trip_id>/travellers")
@login_required
@doc("Add a traveller", body=TravellerBody, tag="Trips")
def add_traveller(trip_id):
    t = get_owned(Trip, trip_id, "trip")
    body = parse_body(TravellerBody)
    db.session.add(Traveller(trip_id=t.id, full_name=body.full_name))
    db.session.commit()
    return ok(trip_dict(t, stats=_stats(t)), 201)


@bp.get("/<trip_id>/reservations")
@login_required
@doc("Reservations in a trip", tag="Trips")
def trip_reservations(trip_id):
    t, _ = viewable_trip(trip_id)
    rows = db.session.execute(db.select(Reservation).where(Reservation.trip_id == t.id)
                              .order_by(Reservation.start_at)).scalars().all()
    changes = db.session.execute(db.select(ReservationChange).where(
        ReservationChange.reservation_id.in_([r.id for r in rows] or [None]))
        .order_by(ReservationChange.detected_at.desc())).scalars().all()
    by_res: dict[str, list] = {}
    for c in changes:
        by_res.setdefault(str(c.reservation_id), []).append(change_dict(c))
    return ok([{**reservation_dict(r), "changes": by_res.get(str(r.id), [])} for r in rows])


@bp.get("/<trip_id>/itinerary")
@login_required
@doc("Itinerary events in a trip, ordered by start time", tag="Trips")
def trip_itinerary(trip_id):
    t, _ = viewable_trip(trip_id)
    rows = db.session.execute(db.select(ItineraryEvent).where(ItineraryEvent.trip_id == t.id)
                              .order_by(ItineraryEvent.start_at)).scalars().all()
    return ok([event_dict(e) for e in rows])


@bp.get("/<trip_id>/documents")
@login_required
@doc("Documents linked to a trip", tag="Trips")
def trip_documents(trip_id):
    t, role = viewable_trip(trip_id)
    if role != "owner":  # biletele si confirmarile au date personale: raman la cine le-a adaugat
        return ok([])
    rows = db.session.execute(db.select(Document).where(Document.trip_id == t.id)
                              .order_by(Document.created_at.desc())).scalars().all()
    return ok([document_dict(d) for d in rows])


@bp.get("/<trip_id>/conflicts")
@login_required
@doc("Deterministic conflict check for a trip", tag="Trips")
def trip_conflicts(trip_id):
    t, role = viewable_trip(trip_id)
    if role != "owner":  # cine doar vede nu schimba nimic si nu primeste notificari de la calatoria altcuiva
        return ok(conflict_engine.as_dicts(conflict_engine.detect(t)))
    items = conflict_engine.check_and_notify(t, current_user())
    db.session.commit()
    return ok(conflict_engine.as_dicts(items))


@bp.post("/<trip_id>/conflicts/explain")
@login_required
@doc("Ask AI to explain the detected conflicts and suggest fixes (text only)", tag="Trips")
def explain_conflicts(trip_id):
    t = get_owned(Trip, trip_id, "trip")
    u = current_user()
    items = conflict_engine.detect(t)
    if not items:
        return ok({"explanation": tr("No conflicts were detected.", locale_of(u)), "provider": None})
    facts = "\n".join(f"- [{c.severity}] {render(c.title)}: {render(c.detail)}" for c in items[:12])
    lang = "Romanian (with correct diacritics)" if locale_of(u) == "ro" else "English"
    req = AIRequest(task=TASK_EXPLANATION, role="fast", temperature=0.2, max_output_tokens=700,
                    system="You explain travel itinerary issues found by a deterministic checker. Use only the facts "
                           f"given. Suggest practical fixes in 3-6 short bullet points. Do not invent times or prices. Write in {lang}.",
                    messages=[ChatMessage.user(f"Trip: {t.name}\nIssues found:\n{facts}")], user_id=u.id)
    try:
        resp = AIRouter().run(req, user=u)
    except AIError as exc:
        return ok({"explanation": None, "provider": None, "unavailable_reason": exc.code})
    return ok({"explanation": resp.text, "provider": resp.provider, "model": resp.model})


@bp.get("/<trip_id>/map")
@login_required
@doc("Located points for the trip map", tag="Trips")
def trip_map(trip_id):
    t, _ = viewable_trip(trip_id)
    points = []
    for e in db.session.execute(db.select(ItineraryEvent).where(ItineraryEvent.trip_id == t.id)).scalars():
        if e.lat is not None and e.type not in ("flight",):
            points.append({"id": str(e.id), "kind": "event", "type": e.type, "status": e.status, "title": e.title,
                           "lat": e.lat, "lon": e.lon, "start_local": event_dict(e)["start_local"]})
    dests = [{"name": d.name, "lat": d.lat, "lon": d.lon} for d in t.destinations if d.lat is not None]
    return ok({"points": points, "destinations": dests})

