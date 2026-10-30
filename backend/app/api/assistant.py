from __future__ import annotations

from flask import Blueprint
from pydantic import BaseModel, Field

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_body, parse_uuid
from app.extensions import db, limiter
from app.models import AgentAction, Conversation, Message, Trip
from app.schemas.serializers import action_dict, conversation_dict, message_dict
from app.services.agent.orchestrator import respond
from app.utils.errors import NotFound

bp = Blueprint("assistant", __name__, url_prefix="/api/v1/assistant")


class ConversationBody(BaseModel):
    trip_id: str | None = None
    title: str | None = Field(default=None, max_length=200)


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


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
    c = Conversation(user_id=u.id, trip_id=trip_id, title=body.title or "New conversation")
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
    body = parse_body(MessageBody)
    reply = respond(current_user(), c, body.content)
    payload = _messages_payload(c)
    payload["reply"] = message_dict(reply)
    return ok(payload, 201)
