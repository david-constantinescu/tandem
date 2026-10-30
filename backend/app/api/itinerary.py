from __future__ import annotations

from flask import Blueprint
from pydantic import BaseModel, Field

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_body, parse_uuid
from app.extensions import db
from app.models import ItineraryEvent, Trip
from app.schemas.serializers import event_dict
from app.services.itinerary import service as itinerary
from app.services.itinerary.conflicts import check_and_notify
from app.services.trips.service import refresh_trip
from app.utils.errors import NotFound

bp = Blueprint("itinerary", __name__, url_prefix="/api/v1/itinerary")


class EventBody(BaseModel):
    trip_id: str
    title: str = Field(min_length=1, max_length=300)
    type: str = "custom"
    status: str = "unbooked"
    start_local: str
    start_tz: str | None = None
    end_local: str | None = None
    end_tz: str | None = None
    location_name: str | None = None
    address: str | None = None
    city: str | None = None
    notes: str | None = None


class EventPatch(BaseModel):
    title: str | None = None
    type: str | None = None
    status: str | None = None
    start_local: str | None = None
    start_tz: str | None = None
    end_local: str | None = None
    end_tz: str | None = None
    location_name: str | None = None
    address: str | None = None
    city: str | None = None
    notes: str | None = None


def _refresh(trip: Trip) -> None:
    refresh_trip(trip, current_user())
    db.session.flush()
    check_and_notify(trip, current_user())


@bp.post("/events")
@login_required
@doc("Add an itinerary event", body=EventBody, tag="Itinerary")
def create_event():
    body = parse_body(EventBody)
    trip = db.session.get(Trip, parse_uuid(body.trip_id, "trip"))
    if trip is None or trip.user_id != current_user().id:
        raise NotFound("Trip not found")
    e = itinerary.create_event(current_user(), trip, body.model_dump(exclude={"trip_id"}), source="manual")
    _refresh(trip)
    db.session.commit()
    return ok(event_dict(e), 201)


@bp.patch("/events/<event_id>")
@login_required
@doc("Edit an itinerary event (users may edit their own plans directly)", body=EventPatch, tag="Itinerary")
def update_event(event_id):
    e = get_owned(ItineraryEvent, event_id, "event")
    body = parse_body(EventPatch)
    itinerary.apply_event_changes(current_user(), e, body.model_dump(exclude_unset=True), actor="user")
    _refresh(db.session.get(Trip, e.trip_id))
    db.session.commit()
    return ok(event_dict(e))


@bp.delete("/events/<event_id>")
@login_required
@doc("Delete an itinerary event", tag="Itinerary")
def delete_event(event_id):
    e = get_owned(ItineraryEvent, event_id, "event")
    trip = db.session.get(Trip, e.trip_id)
    itinerary.delete_event(current_user(), e)
    db.session.flush()
    _refresh(trip)
    db.session.commit()
    return ok({"deleted": True})
