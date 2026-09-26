import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

EVENT_DRAFT = "draft"
EVENT_PUBLISHED = "published"
EVENT_ARCHIVED = "archived"
EVENT_STATUSES = (EVENT_DRAFT, EVENT_PUBLISHED, EVENT_ARCHIVED)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in EVENT_STATUSES) + ")",
            name="events_status_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    venue: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # User id from identity. No foreign key: users live in another database.
    organizer_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(20), default=EVENT_DRAFT, index=True)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    base_price_uah: Mapped[int] = mapped_column(Integer)


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (
        UniqueConstraint("session_id", "row_label", "seat_number", name="seats_position_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    row_label: Mapped[str] = mapped_column(String(10))
    seat_number: Mapped[int] = mapped_column(Integer)
    price_uah: Mapped[int] = mapped_column(Integer)
    # Physically unavailable (broken chair, technical zone). Occupancy by
    # bookings is never stored here; it is owned by booking.
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
