import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

HELD = "HELD"
CONFIRMED = "CONFIRMED"
USED = "USED"
EXPIRED = "EXPIRED"
CANCELLED = "CANCELLED"
BOOKING_STATUSES = (HELD, CONFIRMED, USED, EXPIRED, CANCELLED)
# Statuses in which a booking occupies its seats.
ACTIVE_STATUSES = (HELD, CONFIRMED, USED)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in BOOKING_STATUSES) + ")",
            name="bookings_status_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # User id from identity. No foreign key: users live in another database.
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    # Session id from catalog.
    session_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default=HELD)
    held_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["BookingItem"]] = relationship(
        back_populates="booking", lazy="selectin", order_by="BookingItem.id"
    )


class BookingItem(Base):
    __tablename__ = "booking_items"
    __table_args__ = (
        # At most one booking occupies a seat at any time.
        Index(
            "booking_items_one_active_per_seat",
            "seat_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    # Seat id from catalog.
    seat_id: Mapped[uuid.UUID]
    price_uah: Mapped[int] = mapped_column(Integer)
    # Mirrors "booking status is in ACTIVE_STATUSES"; kept on the item so the
    # partial unique index above can enforce one occupant per seat.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    booking: Mapped[Booking] = relationship(back_populates="items")


class SeatLock(Base):
    """One row per seat ever held. Holds lock these rows with SELECT ... FOR UPDATE,
    so concurrent holds on the same seat are serialised."""

    __tablename__ = "seat_locks"

    seat_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
