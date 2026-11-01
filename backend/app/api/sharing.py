"""impartirea unei calatorii cu familia: membri si link-uri de invitatie"""
from __future__ import annotations

from flask import Blueprint

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_uuid
from app.api.trips import viewable_trip
from app.extensions import db, limiter
from app.i18n import T
from app.models import Trip, TripInvite, TripMember, User
from app.services import sharing
from app.services.audit import audit
from app.services.notifications.service import notify
from app.utils.errors import Forbidden, NotFound
from app.utils.timeutil import iso as iso_utc, utcnow

bp = Blueprint("sharing", __name__, url_prefix="/api/v1")


def _name(u: User) -> str:
    return u.display_name or u.email.split("@")[0]


def _invite_dict(i: TripInvite) -> dict:
    return {"id": str(i.id), "url": sharing.invite_url(i), "created_at": iso_utc(i.created_at),
            "expires_at": iso_utc(i.expires_at), "uses": i.uses}


@bp.get("/trips/<trip_id>/sharing")
@login_required
@doc("Who a trip is shared with, and its active invite links (links only for the owner)", tag="Sharing")
def trip_sharing(trip_id):
    t, role = viewable_trip(trip_id)
    owner = db.session.get(User, t.user_id)
    members = db.session.execute(db.select(TripMember, User).join(User, User.id == TripMember.user_id)
                                 .where(TripMember.trip_id == t.id).order_by(TripMember.joined_at)).all()
    out = {"role": role, "owner": {"user_id": str(owner.id), "name": _name(owner)},
           "members": [{"user_id": str(u.id), "name": _name(u), "joined_at": iso_utc(m.joined_at)} for m, u in members],
           "invites": []}
    if role == "owner":
        invites = db.session.execute(db.select(TripInvite).where(
            TripInvite.trip_id == t.id, TripInvite.revoked_at.is_(None), TripInvite.expires_at > utcnow())
            .order_by(TripInvite.created_at.desc())).scalars().all()
        out["invites"] = [_invite_dict(i) for i in invites]
    return ok(out)


@bp.post("/trips/<trip_id>/invites")
@login_required
@limiter.limit("30 per hour")
@doc("Create an invite link for family or friends to see this trip", tag="Sharing")
def create_invite(trip_id):
    t = get_owned(Trip, trip_id, "trip")
    u = current_user()
    invite = sharing.create_invite(t, u)
    audit(u.id, "trip.invite_created", resource_type="trip", resource_id=t.id)
    db.session.commit()
    return ok(_invite_dict(invite), 201)


@bp.delete("/trips/<trip_id>/invites/<invite_id>")
@login_required
@doc("Turn an invite link off", tag="Sharing")
def revoke_invite(trip_id, invite_id):
    t = get_owned(Trip, trip_id, "trip")
    invite = db.session.get(TripInvite, parse_uuid(invite_id, "invite"))
    if invite is None or invite.trip_id != t.id:
        raise NotFound("Invite not found")
    invite.revoked_at = utcnow()
    audit(current_user().id, "trip.invite_revoked", resource_type="trip", resource_id=t.id)
    db.session.commit()
    return ok({"revoked": True})


@bp.delete("/trips/<trip_id>/members/<user_id>")
@login_required
@doc("Remove someone from a shared trip, or leave it yourself", tag="Sharing")
def remove_member(trip_id, user_id):
    u = current_user()
    t, role = viewable_trip(trip_id)
    target = parse_uuid(user_id, "user")
    if role != "owner" and target != u.id:
        raise Forbidden("Only the owner can remove other people")
    member = db.session.execute(db.select(TripMember).where(
        TripMember.trip_id == t.id, TripMember.user_id == target)).scalar_one_or_none()
    if member is None:
        raise NotFound("Member not found")
    db.session.delete(member)
    audit(u.id, "trip.member_removed", resource_type="trip", resource_id=t.id)
    db.session.commit()
    return ok({"removed": True})


@bp.get("/invites/<token>")
@login_required
@limiter.limit("60 per hour")
@doc("What an invite link is for (shown before the person joins)", tag="Sharing")
def preview_invite(token):
    invite = sharing.find_invite(token)
    t = db.session.get(Trip, invite.trip_id)
    owner = db.session.get(User, t.user_id)
    return ok({"trip_name": t.name, "destination": t.primary_destination,
               "start_date": t.start_date.isoformat() if t.start_date else None,
               "end_date": t.end_date.isoformat() if t.end_date else None,
               "owner_name": _name(owner), "already_in": sharing.role_of(t, current_user()) is not None})


@bp.post("/invites/<token>/accept")
@login_required
@limiter.limit("30 per hour")
@doc("Join a shared trip through an invite link", tag="Sharing")
def accept_invite(token):
    u = current_user()
    invite = sharing.find_invite(token)
    t, joined = sharing.accept_invite(invite, u)
    if joined:
        audit(u.id, "trip.member_joined", resource_type="trip", resource_id=t.id)
        notify(t.user_id, "trip_shared", T("{name} joined {trip}", name=_name(u), trip=t.name),
               T("They can see the plan, bookings and map."), link=f"/trips/{t.id}", dedupe_key=f"joined:{t.id}:{u.id}")
    db.session.commit()
    return ok({"trip_id": str(t.id), "joined": joined})
