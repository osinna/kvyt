"""Endpoints for other services. Not routed by gateway."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import lifecycle
from ..db import get_session
from ..models import HELD, Booking, BookingItem
from ..schemas import Occupancy, OccupiedSeat

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/occupancy", response_model=Occupancy)
async def occupancy(session_id: uuid.UUID, db: AsyncSession = Depends(get_session)) -> Occupancy:
    """Seats of the session currently occupied by a booking."""
    await lifecycle.expire_stale_holds(db, Booking.session_id == session_id)
    await db.commit()
    rows = await db.execute(
        select(BookingItem.seat_id, Booking.status)
        .join(Booking, Booking.id == BookingItem.booking_id)
        .where(Booking.session_id == session_id, BookingItem.is_active)
        .order_by(BookingItem.seat_id)
    )
    return Occupancy(
        session_id=session_id,
        seats=[
            OccupiedSeat(seat_id=seat_id, state="held" if status == HELD else "sold")
            for seat_id, status in rows
        ],
    )
