from __future__ import annotations

from flask import Blueprint
from pydantic import BaseModel, Field

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_body, parse_uuid
from app.i18n import locale_of, tr
from app.extensions import db, limiter
from app.models import AgentAction, Conversation, Message, Trip
from app.schemas.serializers import action_dict, conversation_dict, message_dict
from app.security import throttle
from app.services.agent.orchestrator import respond
from app.utils.errors import NotFound

bp = Blueprint("assistant", __name__, url_prefix="/api/v1/assistant")


class ConversationBody(BaseModel):
    trip_id: str | None = None
    title: str | None = Field(default=None, max_length=200)


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class AttachmentBody(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=10)


def _messages_payload(c: Conversation) -> dict:
    msgs = db.session.execute(db.select(Message).where(Message.conversation_id == c.id)
                              .order_by(Message.created_at)).scalars().all()
    actions = db.session.execute(db.select(AgentAction).where(AgentAction.conversation_id == c.id)).scalars().all()
    return {"conversation": conversation_dict(c), "messages": [message_dict(m) for m in msgs],
            "actions": {str(a.id): action_dict(a) for a in actions}}


@bp.get("/conversations")
@login_required
@doc("Conversations, most recent first", tag="Assistant")
def list_conversations():
    rows = db.session.execute(db.select(Conversation).where(Conversation.user_id == current_user().id)
                              .order_by(Conversation.updated_at.desc()).limit(50)).scalars().all()
    return ok([conversation_dict(c) for c in rows])


@bp.post("/conversations")
@login_required
@doc("Start a conversation, optionally focused on a trip", body=ConversationBody, tag="Assistant")
def create_conversation():
    body = parse_body(ConversationBody)
    u = current_user()
    trip_id = None
    if body.trip_id:
        trip = db.session.get(Trip, parse_uuid(body.trip_id, "trip"))
        if trip is None or trip.user_id != u.id:
            raise NotFound("Trip not found")
        trip_id = trip.id
    c = Conversation(user_id=u.id, trip_id=trip_id, title=body.title or tr("New conversation", locale_of(u)))
    db.session.add(c)
    db.session.commit()
    return ok(conversation_dict(c), 201)


@bp.get("/conversations/<conv_id>")
@login_required
@doc("Conversation with messages and linked actions", tag="Assistant")
def get_conversation(conv_id):
    return ok(_messages_payload(get_owned(Conversation, conv_id, "conversation")))


@bp.delete("/conversations/<conv_id>")
@login_required
@doc("Delete a conversation", tag="Assistant")
def delete_conversation(conv_id):
    c = get_owned(Conversation, conv_id, "conversation")
    db.session.delete(c)
    db.session.commit()
    return ok({"deleted": True})


@bp.get("/conversations/<conv_id>/messages")
@login_required
@doc("Messages in a conversation", tag="Assistant")
def list_messages(conv_id):
    return ok(_messages_payload(get_owned(Conversation, conv_id, "conversation")))


@bp.post("/conversations/<conv_id>/messages")
@login_required
@limiter.limit("60 per hour")
@doc("Send a message; the assistant replies using Tandem's tools", body=MessageBody, tag="Assistant")
def post_message(conv_id):
    c = get_owned(Conversation, conv_id, "conversation")
    # every message can cost AI quota: a shared cap per account, whatever instance serves the request
    throttle.guard("chat", str(current_user().id), limit=80, window_minutes=60)
    body = parse_body(MessageBody)
    reply = respond(current_user(), c, body.content)
    payload = _messages_payload(c)
    payload["reply"] = message_dict(reply)
    return ok(payload, 201)


@bp.post("/conversations/<conv_id>/attachments")
@login_required
@doc("Put uploaded documents (files, photos, pasted emails, links) into the chat; Tandem says what it read",
     body=AttachmentBody, tag="Assistant")
def attach(conv_id):
    from app.models import Document
    from app.services.agent.attachments import describe

    c = get_owned(Conversation, conv_id, "conversation")
    u = current_user()
    docs = []
    for raw in parse_body(AttachmentBody).document_ids:
        d = db.session.get(Document, parse_uuid(raw, "document"))
        if d is None or d.user_id != u.id:
            raise NotFound("Document not found")
        docs.append(d)
    describe(u, c, docs)
    db.session.commit()
    return ok(_messages_payload(c), 201)


@bp.post("/check-in")
@login_required
@limiter.limit("30 per hour")
@doc("Let Tandem look for news about your coming trips and write to you (at most every few hours)", tag="Assistant")
def check_in():
    from app.services.agent import proactive

    u = current_user()
    posted = proactive.check_user(u)
    conv = db.session.execute(db.select(Conversation).where(Conversation.user_id == u.id, Conversation.kind == "updates")).scalars().first()
    return ok({"posted": posted, "updates_conversation_id": str(conv.id) if conv else None})
