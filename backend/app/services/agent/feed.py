"""conversatia de 'noutati' unde tandem scrie primul (vreme, greve, suprapuneri, emailuri importate)"""
from __future__ import annotations

from app.extensions import db
from app.i18n import T, locale_of, tr
from app.models import Conversation, Message, Trip, User
from app.services.cache import cache_get, cache_set
from app.services.notifications.service import notify
from app.utils.timeutil import utcnow


def updates_conversation(user: User, trip: Trip | None = None) -> Conversation:
    conv = db.session.execute(db.select(Conversation).where(
        Conversation.user_id == user.id, Conversation.kind == "updates")).scalars().first()
    if conv is None:
        conv = Conversation(user_id=user.id, trip_id=trip.id if trip else None, kind="updates",
                            title=tr("Updates from Tandem", locale_of(user)))
        db.session.add(conv)
        db.session.flush()
    elif trip is not None and conv.trip_id != trip.id:
        conv.trip_id = trip.id  # asistentul raspunde despre calatoria din ultimul mesaj
    return conv


def already_posted(user: User, key: str) -> bool:
    return bool(cache_get("feed", {"u": str(user.id), "k": key}))


def post(user: User, key: str, content: str, *, trip: Trip | None = None, options: list[str] | None = None,
         references: list[dict] | None = None, notify_title: T | str | None = None) -> Message | None:
    """post once per key. Returns the message, or None when it was already posted."""
    if already_posted(user, key):
        return None
    conv = updates_conversation(user, trip)
    refs = list(references or [])
    if options:
        refs.append({"type": "choices", "id": key[:60], "label": content[:300], "options": options[:4]})
    if trip is not None:
        refs.append({"type": "trip", "id": str(trip.id), "label": trip.name})
    msg = Message(conversation_id=conv.id, role="assistant", content=content, tool_calls=[], references=refs,
                  action_ids=[], provider="tandem", model="proactive")
    db.session.add(msg)
    conv.updated_at = utcnow()
    db.session.flush()
    cache_set("feed", {"u": str(user.id), "k": key}, True, ttl_hours=24 * 60)
    notify(user.id, "assistant_update", notify_title or T("Tandem has an update for you"), content[:200],
           link=f"/assistant/{conv.id}", dedupe_key=f"feed:{key}")
    return msg
