"""Periodic checks run by the worker: upcoming events, cancellation deadlines, approval expiry,
Gmail incremental sync and demo workspace cleanup."""
from __future__ import annotations

import logging
from datetime import timedelta

from app.i18n import T, When
from app.extensions import db
from app.models import AgentAction, DemoTenant, IntegrationConnection, ItineraryEvent, Reservation, User
from app.services.notifications.service import notify
from app.tasks.queue import enqueue
from app.utils.timeutil import to_local, utcnow

log = logging.getLogger("tandem.periodic")


def run_periodic() -> None:
    now = utcnow()
    upcoming_events(now)
    cancellation_deadlines(now)
    expire_actions(now)
    schedule_gmail_sync(now)
    cleanup_demo(now)
    db.session.commit()


def upcoming_events(now) -> None:
    soon = db.session.execute(db.select(ItineraryEvent).where(
        ItineraryEvent.start_at > now, ItineraryEvent.start_at <= now + timedelta(hours=24),
        ItineraryEvent.status.in_(["confirmed", "pending"]))).scalars().all()
    for e in soon:
        local = to_local(e.start_at, e.start_tz)
        notify(e.user_id, "upcoming_event", T("Tomorrow: {title}", title=e.title) if (e.start_at - now) > timedelta(hours=12)
               else T("Coming up: {title}", title=e.title), T("{when} ({tz})", when=When(local), tz=e.start_tz), link=f"/trips/{e.trip_id}",
               dedupe_key=f"upcoming:{e.id}:{e.start_at.isoformat()}")


def cancellation_deadlines(now) -> None:
    rows = db.session.execute(db.select(Reservation).where(
        Reservation.cancellation_deadline > now, Reservation.cancellation_deadline <= now + timedelta(hours=72),
        Reservation.status != "cancelled")).scalars().all()
    for r in rows:
        local = to_local(r.cancellation_deadline, r.start_tz or "UTC")
        notify(r.user_id, "cancellation_deadline", T("Free cancellation ends soon: {title}", title=r.title),
               T("Deadline {when}.", when=When(local)), link=f"/trips/{r.trip_id}" if r.trip_id else None,
               severity="warning", dedupe_key=f"deadline:{r.id}:{r.cancellation_deadline.isoformat()}")


def expire_actions(now) -> None:
    rows = db.session.execute(db.select(AgentAction).where(
        AgentAction.status == "awaiting_approval", AgentAction.expires_at.is_not(None),
        AgentAction.expires_at < now)).scalars().all()
    for a in rows:
        a.status = "expired"


def schedule_gmail_sync(now) -> None:
    rows = db.session.execute(db.select(IntegrationConnection).where(
        IntegrationConnection.provider == "gmail", IntegrationConnection.status == "connected")).scalars().all()
    for c in rows:
        if c.last_sync_at is None or c.last_sync_at < now - timedelta(hours=6):
            enqueue("gmail_sync", {"full": False}, user_id=c.user_id)


def cleanup_demo(now) -> None:
    from app.services.storage import storage
    from app.models import Document

    expired = db.session.execute(db.select(DemoTenant).where(
        DemoTenant.expires_at.is_not(None), DemoTenant.expires_at < now)).scalars().all()
    for tenant in expired:
        users = db.session.execute(db.select(User).where(User.demo_tenant_id == tenant.id)).scalars().all()
        for u in users:
            for d in db.session.execute(db.select(Document).where(Document.user_id == u.id)).scalars():
                if d.storage_key:
                    storage().delete(d.storage_key)
            db.session.delete(u)
        db.session.delete(tenant)
        log.info("removed expired demo workspace %s", tenant.id)
