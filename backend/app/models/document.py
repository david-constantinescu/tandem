from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSONType, Timestamps, UUIDPk, tz_dt, utcnow
from app.security.encryption import EncryptedText

INBOX_STATUSES = (
    "uploaded", "validating", "queued", "processing", "analysing", "awaiting_review",
    "processed", "failed", "duplicate", "ignored",
)
DOCUMENT_SOURCES = ("upload", "paste", "url", "email", "manual", "demo")


class Document(UUIDPk, Timestamps, db.Model):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_user_sha", "user_id", "sha256"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(20), default="upload")
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    email_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    status_detail: Mapped[str] = mapped_column(String(500), default="")
    classification: Mapped[str | None] = mapped_column(String(30), nullable=True)  # travel|unrelated|unknown
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    extraction_method: Mapped[dict] = mapped_column(JSONType, default=dict)  # provider/model/local path used
    processed_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    original_deleted_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)

    records: Mapped[list["ExtractedRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="ExtractedRecord.index"
    )


class ProcessingJob(UUIDPk, db.Model):
    __tablename__ = "processing_jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "run_after"),)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)


class ExtractedRecord(UUIDPk, db.Model):
    """A candidate travel record found in a document, awaiting user review."""

    __tablename__ = "extracted_records"
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer, default=0)
    record_type: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSONType, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    uncertainty_notes: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending_review")  # pending_review|accepted|rejected|change_detected
    extractor: Mapped[dict] = mapped_column(JSONType, default=dict)  # provider, model, prompt_version
    proposed_trip_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    grouping: Mapped[dict] = mapped_column(JSONType, default=dict)  # score, reasons, new_trip proposal
    matched_reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)

    document: Mapped[Document] = relationship(back_populates="records")
    fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class ExtractedField(UUIDPk, db.Model):
    __tablename__ = "extracted_fields"
    __table_args__ = (UniqueConstraint("record_id", "field_name"),)
    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("extracted_records.id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(60))
    evidence: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)  # original text snippet
    value: Mapped[dict | list | str | float | None] = mapped_column(JSONType, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # evidence_found | not_found_in_source | no_source_text | user_corrected | user_confirmed
    verification: Mapped[str] = mapped_column(String(30), default="no_source_text")
    record: Mapped[ExtractedRecord] = relationship(back_populates="fields")


class ProviderFile(UUIDPk, db.Model):
    """Temporary copy of a document held by an AI provider (e.g. Gemini Files API)."""

    __tablename__ = "provider_files"
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_file_id: Mapped[str] = mapped_column(String(255))
    provider_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded|deleted|delete_failed|expired
    uploaded_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    detail: Mapped[str] = mapped_column(String(500), default="")
