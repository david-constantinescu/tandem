from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import JSONType, Timestamps, UUIDPk, tz_dt, utcnow
from app.security.encryption import EncryptedJSON


class Notification(UUIDPk, db.Model):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info | warning | critical | success
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow, index=True)


class AuditLog(UUIDPk, db.Model):
    __tablename__ = "audit_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow, index=True)


class AIUsageRecord(UUIDPk, db.Model):
    __tablename__ = "ai_usage_records"
    __table_args__ = (Index("ix_ai_usage_user_created", "user_id", "created_at"),)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(80))
    task: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))  # ok | error | rate_limited | rejected | invalid_output | cached
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)


class CacheEntry(db.Model):
    """Small key/value cache (AI responses, geocoding, provider searches)."""

    __tablename__ = "cache_entries"
    namespace: Mapped[str] = mapped_column(String(40), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list] = mapped_column(JSONType)
    expires_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)


class ProviderStatus(db.Model):
    """Last observed health/quota state of an AI or travel provider (application-wide)."""

    __tablename__ = "provider_status"
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # ai | travel
    state: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSONType, default=dict)
    cooldown_until: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)


class IntegrationConnection(UUIDPk, Timestamps, db.Model):
    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))  # gmail
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|connected|error|disconnected
    account_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    scopes: Mapped[list] = mapped_column(JSONType, default=list)
    tokens: Mapped[dict | None] = mapped_column(EncryptedJSON, nullable=True)
    oauth_state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    history_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class EmailCandidate(UUIDPk, db.Model):
    __tablename__ = "email_candidates"
    __table_args__ = (UniqueConstraint("user_id", "message_id"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("integration_connections.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str] = mapped_column(String(64))
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), default="")
    sender: Mapped[str] = mapped_column(String(320), default="")
    received_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    snippet: Mapped[str] = mapped_column(String(500), default="")
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="candidate")  # candidate|imported|skipped
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)


class BrowserTask(UUIDPk, Timestamps, db.Model):
    """State record for user-guided website workflows (design scaffold; see docs/AGENT_ARCHITECTURE.md)."""

    __tablename__ = "browser_tasks"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    site: Mapped[str] = mapped_column(String(200))
    # not_started|searching|navigating|waiting_for_user|awaiting_approval|submitting|verifying|
    # completed|failed|blocked|requires_manual
    state: Mapped[str] = mapped_column(String(30), default="not_started")
    goal: Mapped[str] = mapped_column(Text, default="")
    stop_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    log: Mapped[list] = mapped_column(JSONType, default=list)
