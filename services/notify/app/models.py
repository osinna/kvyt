import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

BOOKING_CONFIRMED = "booking_confirmed"
BOOKING_CANCELLED = "booking_cancelled"
NOTIFICATION_TYPES = (BOOKING_CONFIRMED, BOOKING_CANCELLED)
SENT = "SENT"

ONE_PER_EVENT_INDEX = "notifications_one_per_booking_type"
ONE_PER_EVENT_SQL = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {ONE_PER_EVENT_INDEX} "
    "ON notifications (booking_id, type)"
)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "type IN (" + ", ".join(f"'{t}'" for t in NOTIFICATION_TYPES) + ")",
            name="notifications_type_check",
        ),
        # One event, one notification: a redelivered message must not add another.
        Index(ONE_PER_EVENT_INDEX, "booking_id", "type", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # User id from identity, booking id from booking: no foreign keys across databases.
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(index=True)
    type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default=SENT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
