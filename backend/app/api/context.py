"""context live pt calatorie: vremea pe zile, stiri cu greve/proteste si variante reale de drum"""
from __future__ import annotations

from flask import Blueprint
from pydantic import BaseModel, Field

from app.api._core import doc, get_owned, login_required, ok, parse_query
from app.extensions import limiter
from app.models import Trip
from app.services.context import journeys, news, weather

bp = Blueprint("context", __name__, url_prefix="/api/v1")


@bp.get("/trips/<trip_id>/context")
@login_required
@limiter.limit("60 per hour")
@doc("Weather for the trip's days and recent local news about strikes, protests and closures", tag="Trips")
def trip_context(trip_id):
    t = get_owned(Trip, trip_id, "trip")
    return ok({"weather": weather.for_trip(t), "news": news.for_trip(t)})


class JourneyQuery(BaseModel):
    origin: str = Field(min_length=2, max_length=80)
    destination: str = Field(min_length=2, max_length=80)
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    mode: str | None = Field(default=None, pattern="^(train|bus|flight)$")


@bp.get("/journeys")
@login_required
@doc("Real journey planners and official operators for a route, with the route filled in", tag="Explore")
def journey_options():
    q = parse_query(JourneyQuery)
    return ok(journeys.options(q.origin, q.destination, day=q.date, mode=q.mode))
