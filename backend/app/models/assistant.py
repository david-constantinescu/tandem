from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import JSONType, Timestamps, UUIDPk, tz_dt, utcnow

# Lifecycle of anything the assistant (or the user via Discover) wants to do.
ACTION_STATUSES = (
    "suggested", "prepared", "awaiting_approval", "in_progress", "completed", "failed",
    "requires_manual", "rejected", "expired", "cancelled",
)


class Conversation(UUIDPk, Timestamps, db.Model):
    __tablename__ = "conversations"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    # "chat" for the user's own conversations; "updates" for the one where Tandem writes first (weather, strikes,
    # clashes, imported email). The user can answer there like anywhere else.
    kind: Mapped[str] = mapped_column(String(20), default="chat", server_default="chat")


class Message(UUIDPk, db.Model):
    __tablename__ = "messages"
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[list] = mapped_column(JSONType, default=list)  # [{name, args_summary, status, summary}]
    references: Mapped[list] = mapped_column(JSONType, default=list)  # [{type, id, label}]
    action_ids: Mapped[list] = mapped_column(JSONType, default=list)
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)


class AgentAction(UUIDPk, Timestamps, db.Model):
    """A proposed or executed action. Consequential actions always pass through an Approval."""

    __tablename__ = "agent_actions"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    # book_activity | itinerary_update | itinerary_delete | apply_reservation_change | link_out
    action_type: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="awaiting_approval", index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    consequences: Mapped[list] = mapped_column(JSONType, default=list)
    cancellation_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    external: Mapped[bool] = mapped_column(default=False)  # touches an outside provider
    created_by: Mapped[str] = mapped_column(String(20), default="assistant")  # assistant | user
    expires_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)


class Approval(UUIDPk, db.Model):
    __tablename__ = "approvals"
    action_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agent_actions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    decision: Mapped[str] = mapped_column(String(20))  # approved | rejected
    payload_hash: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(String(500), default="")
    decided_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)


class ProviderBooking(UUIDPk, Timestamps, db.Model):
    __tablename__ = "provider_bookings"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_actions.id", ondelete="SET NULL"), nullable=True
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    provider_booking_id: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30))
    simulated: Mapped[bool] = mapped_column(default=False)
    verified_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    response_summary: Mapped[dict] = mapped_column(JSONType, default=dict)


class SavedActivity(UUIDPk, db.Model):
    __tablename__ = "saved_activities"
    __table_args__ = (UniqueConstraint("user_id", "provider", "provider_item_id"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    provider_item_id: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)
