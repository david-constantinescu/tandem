from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSONType, Timestamps, UUIDPk, tz_dt, utcnow
from app.security.encryption import EncryptedText

# Modes for external AI processing, enforced by the AI router.
AI_MODE_OFF = "off"  # local parsing only; nothing leaves Tandem
AI_MODE_TEXT = "text_only"  # locally extracted text may be sent; original files never leave Tandem
AI_MODE_FULL = "full"  # original files may be sent to providers that officially support them
AI_MODES = (AI_MODE_OFF, AI_MODE_TEXT, AI_MODE_FULL)


class DemoTenant(UUIDPk, Timestamps, db.Model):
    __tablename__ = "demo_tenants"
    label: Mapped[str] = mapped_column(String(120))
    expires_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)


class User(UUIDPk, Timestamps, db.Model):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    home_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    home_airport: Mapped[str | None] = mapped_column(String(8), nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="en")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    demo_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("demo_tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)

    preferences: Mapped["UserPreference"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    ai_settings: Mapped["UserAISettings"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserSession(UUIDPk, db.Model):
    __tablename__ = "user_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(tz_dt())
    last_seen_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    revoked_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)


DEFAULT_NOTIFICATION_PREFS = {
    "document_processed": True,
    "document_failed": True,
    "reservation_detected": True,
    "trip_created": True,
    "reservation_changed": True,
    "conflict_detected": True,
    "upcoming_event": True,
    "cancellation_deadline": True,
    "approval_required": True,
    "booking_result": True,
    "integration_failure": True,
}


class UserPreference(db.Model):
    __tablename__ = "user_preferences"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    interests: Mapped[list] = mapped_column(JSONType, default=list)
    pace: Mapped[str] = mapped_column(String(20), default="balanced")
    budget: Mapped[str] = mapped_column(String(20), default="moderate")
    accessibility_needs: Mapped[str] = mapped_column(String(500), default="")
    default_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    notification_prefs: Mapped[dict] = mapped_column(JSONType, default=lambda: dict(DEFAULT_NOTIFICATION_PREFS))
    retain_original_documents: Mapped[bool] = mapped_column(Boolean, default=True)
    # When on, high-confidence records whose key fields were verified against the source are
    # added to the matching trip without a manual review step.
    auto_organize: Mapped[bool] = mapped_column(Boolean, default=False)
    # Private calendar subscription link. The token is kept encrypted so Settings can show the link again,
    # and looked up by its keyed hash. Regenerating replaces both, which revokes the old link.
    calendar_token: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    calendar_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    calendar_token_created_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    user: Mapped[User] = relationship(back_populates="preferences")


class UserAISettings(db.Model):
    __tablename__ = "user_ai_settings"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    mode: Mapped[str] = mapped_column(String(20), default=AI_MODE_OFF)
    allowed_providers: Mapped[dict] = mapped_column(
        JSONType, default=lambda: {"gemini": True, "zai": True, "groq": True}
    )
    preferred_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    user: Mapped[User] = relationship(back_populates="ai_settings")
