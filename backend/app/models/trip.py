from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSONType, Timestamps, UUIDPk, tz_dt, utcnow

RESERVATION_TYPES = (
    "flight", "train", "bus", "car_rental", "hotel", "activity", "tour", "museum",
    "restaurant", "transfer", "ferry", "event", "other",
)
RESERVATION_STATUSES = ("confirmed", "pending", "cancelled", "unknown")
EVENT_TYPES = (
    "flight", "train", "bus", "car_rental", "hotel_checkin", "hotel_checkout", "activity", "tour",
    "museum", "restaurant", "transfer", "ferry", "meeting", "free_time", "travel_time", "custom",
    "reminder", "event",
)
EVENT_STATUSES = ("confirmed", "pending", "suggested", "unbooked", "cancelled", "completed")
VERIFICATION_STATES = ("verified", "user_confirmed", "unverified")


class Trip(UUIDPk, Timestamps, db.Model):
    __tablename__ = "trips"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_destination: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_via: Mapped[str] = mapped_column(String(20), default="user")  # user | auto | demo
    grouping: Mapped[dict] = mapped_column(JSONType, default=dict)  # why records were grouped
    known_conflicts: Mapped[list] = mapped_column(JSONType, default=list)  # conflict keys already notified

    destinations: Mapped[list["TripDestination"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="TripDestination.position"
    )
    travellers: Mapped[list["Traveller"]] = relationship(back_populates="trip", cascade="all, delete-orphan")


class TripDestination(UUIDPk, db.Model):
    __tablename__ = "trip_destinations"
    trip_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    arrive_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    depart_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    trip: Mapped[Trip] = relationship(back_populates="destinations")


class Traveller(UUIDPk, db.Model):
    __tablename__ = "travellers"
    trip_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    trip: Mapped[Trip] = relationship(back_populates="travellers")


class Reservation(UUIDPk, Timestamps, db.Model):
    __tablename__ = "reservations"
    __table_args__ = (Index("ix_reservations_user_ref", "user_id", "booking_reference"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    title: Mapped[str] = mapped_column(String(300))
    provider_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    booking_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str | None] = mapped_column(String(200), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    start_tz: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    end_tz: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    travellers: Mapped[list] = mapped_column(JSONType, default=list)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)  # flight number, seat, terminal, room...
    cancellation_deadline: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    cancellation_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification: Mapped[str] = mapped_column(String(20), default="unverified")
    created_via: Mapped[str] = mapped_column(String(20), default="manual")  # extraction|manual|booking|demo


class ReservationChange(UUIDPk, db.Model):
    __tablename__ = "reservation_changes"
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("reservations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    extracted_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("extracted_records.id", ondelete="SET NULL"), nullable=True
    )
    changes: Mapped[dict] = mapped_column(JSONType, default=dict)  # field -> {"old": .., "new": ..}
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|applied|dismissed
    summary: Mapped[str] = mapped_column(String(500), default="")
    detected_at: Mapped[datetime] = mapped_column(tz_dt(), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)


class ItineraryEvent(UUIDPk, Timestamps, db.Model):
    __tablename__ = "itinerary_events"
    __table_args__ = (Index("ix_itinerary_trip_start", "trip_id", "start_at"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("reservations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    title: Mapped[str] = mapped_column(String(300))
    notes: Mapped[str] = mapped_column(Text, default="")
    start_at: Mapped[datetime] = mapped_column(tz_dt())
    start_tz: Mapped[str] = mapped_column(String(64))
    end_at: Mapped[datetime | None] = mapped_column(tz_dt(), nullable=True)
    end_tz: Mapped[str | None] = mapped_column(String(64), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    location_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    # transport events have a separate arrival location
    end_location_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    end_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    end_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # reservation|manual|assistant|demo
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
