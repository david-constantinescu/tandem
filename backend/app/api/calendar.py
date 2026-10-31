"""export de calendar: un .ics pe calatorie si un feed privat pt apple/google calendar"""
from __future__ import annotations

import re
import secrets
from datetime import timedelta

from flask import Blueprint, Response, current_app

from app.api._core import current_user, doc, get_owned, login_required, ok
from app.extensions import db, limiter
from app.models import ItineraryEvent, Trip
from app.models.user import UserPreference
from app.security.encryption import hash_token
from app.services.audit import audit
from app.services.calendar_ics import EXPORTED_STATUSES, build_calendar
from app.utils.errors import NotFound
from app.utils.timeutil import iso, utcnow

bp = Blueprint("calendar", __name__, url_prefix="/api/v1/calendar")

FEED_HISTORY = timedelta(days=30)  # the feed keeps a month of past events, then lets them drop off
FEED_LIMIT = 2000


def _app_url() -> str:
    return current_app.config["FRONTEND_URL"].rstrip("/")


def _events_query(user_id):
    return (db.select(ItineraryEvent).join(Trip, Trip.id == ItineraryEvent.trip_id)
            .where(ItineraryEvent.user_id == user_id, ItineraryEvent.status.in_(EXPORTED_STATUSES),
                   Trip.is_cancelled.is_(False))
            .order_by(ItineraryEvent.start_at))


def _ics_response(body: str, filename: str) -> Response:
    resp = Response(body, mimetype="text/calendar")
    resp.headers["Content-Type"] = "text/calendar; charset=utf-8"
    # inline: iOS Safari offers "Add to Calendar" for the whole file instead of a download
    resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    resp.headers["Cache-Control"] = "private, no-cache"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


def _subscription_dict(p: UserPreference) -> dict:
    if not p.calendar_token:
        return {"active": False, "url": None, "webcal_url": None, "created_at": None}
    url = f"{current_app.config['BACKEND_URL'].rstrip('/')}/api/v1/calendar/feed/{p.calendar_token}.ics"
    return {"active": True, "url": url, "webcal_url": re.sub(r"^https?://", "webcal://", url),
            "created_at": iso(p.calendar_token_created_at)}


@bp.get("/subscription")
@login_required
@doc("Private calendar subscription link", tag="Calendar")
def get_subscription():
    return ok(_subscription_dict(current_user().preferences))


@bp.post("/subscription")
@login_required
@doc("Create or reset the calendar subscription link (the previous link stops working)", tag="Calendar")
def reset_subscription():
    u = current_user()
    p = u.preferences
    token = secrets.token_urlsafe(32)
    p.calendar_token, p.calendar_token_hash, p.calendar_token_created_at = token, hash_token(token), utcnow()
    audit(u.id, "calendar.subscription_reset")
    db.session.commit()
    return ok(_subscription_dict(p))


@bp.delete("/subscription")
@login_required
@doc("Turn off the calendar subscription link", tag="Calendar")
def delete_subscription():
    u = current_user()
    p = u.preferences
    p.calendar_token = p.calendar_token_hash = p.calendar_token_created_at = None
    audit(u.id, "calendar.subscription_revoked")
    db.session.commit()
    return ok(_subscription_dict(p))


@bp.get("/feed/<token>.ics")
@limiter.limit("120 per hour")
@doc("Subscription feed of all trips (the token in the URL is the credential)", tag="Calendar", auth=False)
def feed(token):
    if len(token) > 100:
        raise NotFound("Calendar not found")
    p = db.session.execute(db.select(UserPreference).where(
        UserPreference.calendar_token_hash == hash_token(token))).scalar()
    if p is None:
        raise NotFound("Calendar not found")
    rows = db.session.execute(_events_query(p.user_id).where(ItineraryEvent.start_at >= utcnow() - FEED_HISTORY)
                              .limit(FEED_LIMIT)).scalars().all()
    return _ics_response(build_calendar(rows, name="Tandem trips", app_url=_app_url()), "tandem-trips.ics")


@bp.get("/trips/<trip_id>.ics")
@login_required
@doc("One trip as an .ics file to add to a calendar", tag="Calendar")
def trip_ics(trip_id):
    t = get_owned(Trip, trip_id, "trip")
    rows = db.session.execute(_events_query(t.user_id).where(ItineraryEvent.trip_id == t.id)).scalars().all()
    slug = re.sub(r"[^a-z0-9]+", "-", t.name.lower()).strip("-")[:60] or "trip"
    return _ics_response(build_calendar(rows, name=t.name, app_url=_app_url()), f"{slug}.ics")
