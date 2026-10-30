from __future__ import annotations

from datetime import date

from flask import Blueprint
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_body, parse_uuid
from app.extensions import db, limiter
from app.models import SavedActivity, Trip
from app.schemas.serializers import action_dict
from app.services.agent.approvals import propose_booking
from app.services.providers import activities as activity_service
from app.services.providers.base import ActivitySearchRequest, ProviderCapabilityError, ProviderRequestError
from app.services.providers.registry import adapters_for, get_adapter
from app.utils.errors import APIError, NotFound

bp = Blueprint("activities", __name__, url_prefix="/api/v1/activities")


class SearchBody(BaseModel):
    trip_id: str | None = None
    location: str | None = Field(default=None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    start_after: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_before: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    max_price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="EUR", pattern="^[A-Z]{3}$")
    categories: list[str] = Field(default_factory=list)
    query: str | None = Field(default=None, max_length=200)
    group_size: int = Field(default=1, ge=1, le=20)
    max_duration_minutes: int | None = Field(default=None, ge=15)
    accessible_only: bool = False
    radius_km: float = Field(default=4.0, gt=0, le=25)
    providers: list[str] | None = None


class AvailabilityBody(BaseModel):
    date: date
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    participants: int = Field(default=1, ge=1, le=20)


class ProposalBody(BaseModel):
    provider: str
    provider_item_id: str
    date: date
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    participants: int = Field(default=1, ge=1, le=20)
    trip_id: str | None = None
    replaces_event_id: str | None = None


class SaveBody(BaseModel):
    provider: str
    provider_item_id: str
    trip_id: str | None = None
    data: dict = Field(default_factory=dict)


def _trip(trip_id: str | None) -> Trip | None:
    if not trip_id:
        return None
    t = db.session.get(Trip, parse_uuid(trip_id, "trip"))
    if t is None or t.user_id != current_user().id:
        raise NotFound("Trip not found")
    return t


@bp.get("/providers")
@login_required
@doc("Activity providers available to this account and their capability states", tag="Activities")
def providers():
    return ok([a.capabilities() for a in adapters_for(current_user())])


@bp.post("/search")
@login_required
@limiter.limit("120 per hour")
@doc("Search activities across providers, optionally checking fit against a trip's itinerary", body=SearchBody,
     tag="Activities")
def search():
    body = parse_body(SearchBody)
    trip = _trip(body.trip_id)
    req = ActivitySearchRequest(**body.model_dump(exclude={"trip_id", "providers"}))
    return ok(activity_service.search(current_user(), req, trip=trip, providers=body.providers))


@bp.get("/<provider>/<path:item_id>")
@login_required
@doc("Activity details from its provider", tag="Activities")
def details(provider, item_id):
    adapter = get_adapter(current_user(), provider)
    try:
        return ok(adapter.get_details(item_id).to_dict())
    except (ProviderRequestError, ProviderCapabilityError) as exc:
        raise APIError(str(exc), code=getattr(exc, "code", "provider_error"), status=502) from exc


@bp.post("/<provider>/<path:item_id>/availability")
@login_required
@doc("Live availability and price for a date/time", body=AvailabilityBody, tag="Activities")
def availability(provider, item_id):
    body = parse_body(AvailabilityBody)
    adapter = get_adapter(current_user(), provider)
    try:
        return ok(adapter.check_availability(item_id, body.date.isoformat(), body.time, body.participants).to_dict())
    except (ProviderRequestError, ProviderCapabilityError) as exc:
        raise APIError(str(exc), code=getattr(exc, "code", "provider_error"), status=502) from exc


@bp.post("/proposals")
@login_required
@doc("Prepare a booking proposal (re-checks live price/availability). Requires approval to book.",
     body=ProposalBody, tag="Activities")
def create_proposal():
    body = parse_body(ProposalBody)
    try:
        action = propose_booking(current_user(), provider=body.provider, item_id=body.provider_item_id,
                                 day=body.date.isoformat(), time=body.time, participants=body.participants,
                                 trip=_trip(body.trip_id), created_by="user", replaces_event_id=body.replaces_event_id)
    except (ProviderRequestError, ProviderCapabilityError) as exc:
        raise APIError(str(exc), code=getattr(exc, "code", "provider_error"), status=502) from exc
    db.session.commit()
    return ok(action_dict(action), 201)


@bp.get("/saved")
@login_required
@doc("Saved activities", tag="Activities")
def saved():
    rows = db.session.execute(db.select(SavedActivity).where(SavedActivity.user_id == current_user().id)
                              .order_by(SavedActivity.created_at.desc())).scalars().all()
    return ok([{"id": str(s.id), "provider": s.provider, "provider_item_id": s.provider_item_id,
                "trip_id": str(s.trip_id) if s.trip_id else None, "data": s.data,
                "created_at": s.created_at.isoformat()} for s in rows])


@bp.post("/saved")
@login_required
@doc("Save an activity for later", body=SaveBody, tag="Activities")
def save():
    body = parse_body(SaveBody)
    u = current_user()
    get_adapter(u, body.provider)
    keep = {k: body.data.get(k) for k in ("title", "price", "currency", "duration_minutes", "address", "booking_url",
                                          "source_label", "simulated", "categories", "lat", "lon", "image_url")}
    item = SavedActivity(user_id=u.id, provider=body.provider, provider_item_id=body.provider_item_id,
                         trip_id=_trip(body.trip_id).id if body.trip_id else None, data=keep)
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return ok({"saved": True, "already": True})
    return ok({"id": str(item.id), "saved": True}, 201)


@bp.delete("/saved/<saved_id>")
@login_required
@doc("Remove a saved activity", tag="Activities")
def unsave(saved_id):
    item = get_owned(SavedActivity, saved_id, "saved activity")
    db.session.delete(item)
    db.session.commit()
    return ok({"deleted": True})
