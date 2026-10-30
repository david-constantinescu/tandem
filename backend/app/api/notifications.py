from __future__ import annotations

from flask import Blueprint, request

from app.api._core import current_user, doc, get_owned, login_required, ok
from app.extensions import db
from app.models import Notification
from app.schemas.serializers import notification_dict
from app.utils.timeutil import utcnow

bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")


@bp.get("")
@login_required
@doc("Notifications (?unread=true)", tag="Notifications")
def list_notifications():
    u = current_user()
    q = db.select(Notification).where(Notification.user_id == u.id)
    if request.args.get("unread") == "true":
        q = q.where(Notification.read_at.is_(None))
    rows = db.session.execute(q.order_by(Notification.created_at.desc()).limit(60)).scalars().all()
    unread = db.session.execute(db.select(db.func.count(Notification.id)).where(
        Notification.user_id == u.id, Notification.read_at.is_(None))).scalar()
    return ok([notification_dict(n) for n in rows], meta={"unread": unread})


@bp.post("/<note_id>/read")
@login_required
@doc("Mark a notification read", tag="Notifications")
def mark_read(note_id):
    n = get_owned(Notification, note_id, "notification")
    n.read_at = n.read_at or utcnow()
    db.session.commit()
    return ok(notification_dict(n))


@bp.post("/read-all")
@login_required
@doc("Mark all notifications read", tag="Notifications")
def mark_all_read():
    u = current_user()
    for n in db.session.execute(db.select(Notification).where(
            Notification.user_id == u.id, Notification.read_at.is_(None))).scalars():
        n.read_at = utcnow()
    db.session.commit()
    return ok({"done": True})
