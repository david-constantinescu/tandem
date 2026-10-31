"""fisierele puse in chat: apar in conversatie si tandem zice ce a citit din ele"""
from __future__ import annotations

from datetime import timedelta

from app.extensions import db
from app.i18n import locale_of, tr
from app.models import Conversation, Document, Message, Reservation, User
from app.services.cache import cache_get, cache_set
from app.utils.timeutil import iso_local, utcnow

READING = ("queued", "processing", "uploaded")
KIND = {"flight": "Flight", "hotel": "Stay", "train": "Train", "bus": "Bus", "museum": "Ticket", "tour": "Tour",
        "restaurant": "Restaurant", "activity": "Activity", "car_rental": "Car", "ferry": "Ferry"}


def _line(user: User, d: Document, loc: str) -> tuple[str, list[dict]]:
    refs = [{"type": "document", "id": str(d.id), "label": d.filename[:60]}]
    if d.status == "duplicate":
        return tr("**{name}**: I already have this one.", loc, name=d.filename), refs
    if d.status == "failed":
        return tr("**{name}**: I couldn't read it ({why}).", loc, name=d.filename, why=d.status_detail or "?"), refs
    if d.status in READING:
        return tr("**{name}**: still reading it; I'll tell you when it's done.", loc, name=d.filename), refs
    if d.classification == "unrelated":
        return tr("**{name}**: this doesn't look like a booking.", loc, name=d.filename), refs
    parts = []
    from app.models import ExtractedRecord

    records = db.session.execute(db.select(ExtractedRecord).where(ExtractedRecord.document_id == d.id)
                                 .order_by(ExtractedRecord.index)).scalars().all()
    for r in records:
        data = r.data or {}
        title = data.get("title") or data.get("provider_name") or tr(KIND.get(r.record_type, "Booking"), loc)
        when = data.get("start_local") or ""
        res = db.session.get(Reservation, r.reservation_id) if r.reservation_id else None
        if res is not None:
            when = iso_local(res.start_at, res.start_tz)[:16].replace("T", " ") if res.start_at else when
            refs.append({"type": "reservation", "id": str(res.id), "label": res.title, "trip_id": str(res.trip_id)})
        state = tr("added to your trip", loc) if r.status == "accepted" else \
            tr("a change to an existing booking, waiting for your OK", loc) if r.status == "change_detected" else \
            tr("check it before I add it", loc) if r.status == "pending_review" else tr("skipped", loc)
        parts.append(f"{title}{(' · ' + when.replace('T', ' ')[:16]) if when else ''} — {state}")
    if not parts:
        return tr("**{name}**: I didn't find any bookings in it.", loc, name=d.filename), refs
    return f"**{d.filename}**: " + "; ".join(parts), refs


def describe(user: User, conv: Conversation, docs: list[Document]) -> Message:
    loc = locale_of(user)
    names = ", ".join(d.filename for d in docs)
    now = utcnow()
    db.session.add(Message(conversation_id=conv.id, role="user", content=f"📎 {names}", created_at=now,
                           references=[{"type": "document", "id": str(d.id), "label": d.filename[:60]} for d in docs]))
    for d in docs:
        if d.status in READING:  # raspundem iar aici cand termina de citit
            cache_set("doc_chat", str(d.id), str(conv.id), ttl_hours=24)
    lines, refs = [], []
    for d in docs:
        text, r = _line(user, d, loc)
        lines.append(f"- {text}")
        refs.extend(r)
    waiting = any(d.status == "awaiting_review" for d in docs)
    body = tr("Here's what I read:", loc) + "\n" + "\n".join(lines)
    if waiting:
        body += "\n\n" + tr("Open the document to check what I found; nothing uncertain goes into your trip until you say so.", loc)
    msg = Message(conversation_id=conv.id, role="assistant", content=body, references=refs, tool_calls=[],
                  action_ids=[], provider="tandem", model="reader", created_at=now + timedelta(milliseconds=5))
    db.session.add(msg)
    conv.updated_at = utcnow()
    if conv.title in ("New conversation", tr("New conversation", "ro")):
        conv.title = names[:80]
    db.session.flush()
    return msg


def follow_up(user: User, doc: Document) -> None:
    """called when a document finishes reading: if it was added in a chat while still being read, answer there"""
    conv_id = cache_get("doc_chat", str(doc.id))
    if not conv_id:
        return
    conv = db.session.get(Conversation, __import__("uuid").UUID(conv_id))
    if conv is None or conv.user_id != user.id:
        return
    cache_set("doc_chat", str(doc.id), None, ttl_hours=0.001)
    text, refs = _line(user, doc, locale_of(user))
    db.session.add(Message(conversation_id=conv.id, role="assistant", content=text, references=refs, tool_calls=[],
                           action_ids=[], provider="tandem", model="reader", created_at=utcnow()))
    conv.updated_at = utcnow()
