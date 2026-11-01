"""calatorii impartite: cine le poate vedea si link-urile de invitatie"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models import Trip, TripInvite, TripMember, User
from app.security.encryption import hash_token
from app.utils.errors import Conflict, NotFound
from app.utils.timeutil import utcnow

INVITE_DAYS = 14
MAX_ACTIVE_INVITES = 10
MAX_MEMBERS = 12


def role_of(trip: Trip, user: User) -> str | None:
    """'owner', 'member' sau None cand omul nu are acces"""
    if trip.user_id == user.id:
        return "owner"
    member = db.session.execute(db.select(TripMember.id).where(
        TripMember.trip_id == trip.id, TripMember.user_id == user.id)).first()
    return "member" if member else None


def shared_trip_ids(user: User) -> list[uuid.UUID]:
    return list(db.session.execute(db.select(TripMember.trip_id).where(TripMember.user_id == user.id)).scalars())


def invite_url(invite: TripInvite) -> str:
    return f"{current_app.config['FRONTEND_URL'].rstrip('/')}/join/{invite.token}"


def create_invite(trip: Trip, owner: User) -> TripInvite:
    now = utcnow()
    active = db.session.execute(db.select(db.func.count(TripInvite.id)).where(
        TripInvite.trip_id == trip.id, TripInvite.revoked_at.is_(None), TripInvite.expires_at > now)).scalar() or 0
    if active >= MAX_ACTIVE_INVITES:
        raise Conflict("Too many active invite links; remove one first", code="too_many_invites")
    token = secrets.token_urlsafe(24)
    invite = TripInvite(trip_id=trip.id, created_by=owner.id, token=token, token_hash=hash_token(token),
                        expires_at=now + timedelta(days=INVITE_DAYS))
    db.session.add(invite)
    db.session.flush()
    return invite


def find_invite(token: str) -> TripInvite:
    """un link gresit, expirat sau retras arata la fel: nu dam de gol ce exista"""
    if not token or len(token) > 100:
        raise NotFound("This invite link isn't valid any more", code="invite_invalid")
    invite = db.session.execute(db.select(TripInvite).where(TripInvite.token_hash == hash_token(token))).scalar_one_or_none()
    if invite is None or invite.revoked_at is not None or invite.expires_at < utcnow():
        raise NotFound("This invite link isn't valid any more", code="invite_invalid")
    return invite


def accept_invite(invite: TripInvite, user: User) -> tuple[Trip, bool]:
    trip = db.session.get(Trip, invite.trip_id)
    if trip is None:
        raise NotFound("This invite link isn't valid any more", code="invite_invalid")
    if role_of(trip, user) is not None:
        return trip, False
    count = db.session.execute(db.select(db.func.count(TripMember.id)).where(TripMember.trip_id == trip.id)).scalar() or 0
    if count >= MAX_MEMBERS:
        raise Conflict("This trip already has the most people it can share with", code="trip_full")
    db.session.add(TripMember(trip_id=trip.id, user_id=user.id, role="member"))
    invite.uses += 1
    db.session.flush()
    return trip, True
