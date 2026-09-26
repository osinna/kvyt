"""Booking state transitions, including lazy hold expiry.

There is no background worker: a HELD booking whose held_until has passed is
turned into EXPIRED by whichever read touches it first.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ColumnElement, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CANCELLED, EXPIRED, HELD, Booking, BookingItem


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def expire_stale_holds(db: AsyncSession, *where: ColumnElement[bool]) -> None:
    """Marks overdue holds matching `where` as EXPIRED and frees their seats.

    Runs as bulk UPDATEs, so call it before loading the affected bookings.
    Does not commit: the caller's transaction owns the change.
    """
    expired_ids = (
        await db.scalars(
            update(Booking)
            .where(Booking.status == HELD, Booking.held_until < utcnow(), *where)
            .values(status=EXPIRED)
            .returning(Booking.id)
            .execution_options(synchronize_session=False)
        )
    ).all()
    if expired_ids:
        await release_seats(db, list(expired_ids))


async def release_seats(db: AsyncSession, booking_ids: list[uuid.UUID]) -> None:
    await db.execute(
        update(BookingItem)
        .where(BookingItem.booking_id.in_(booking_ids))
        .values(is_active=False)
        .execution_options(synchronize_session=False)
    )


async def cancel(db: AsyncSession, booking: Booking) -> None:
    booking.status = CANCELLED
    await release_seats(db, [booking.id])


async def load_for_update(db: AsyncSession, booking_id: uuid.UUID) -> Booking | None:
    return await db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
