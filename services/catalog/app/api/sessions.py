import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import booking_client
from ..db import get_session
from ..models import Seat, Session
from ..queries import get_public_session
from ..schemas import SeatOut, SessionOut, SessionSeats

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionOut)
async def get_session_by_id(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_session)
) -> Session:
    return await get_public_session(db, session_id)


@router.get("/{session_id}/seats", response_model=SessionSeats)
async def list_session_seats(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_session)
) -> SessionSeats:
    await get_public_session(db, session_id)
    occupied = await booking_client.fetch_occupancy(session_id)
    seats = await db.scalars(
        select(Seat)
        .where(Seat.session_id == session_id)
        .order_by(Seat.row_label, Seat.seat_number)
    )
    return SessionSeats(
        session_id=session_id,
        seats=[
            SeatOut(
                id=seat.id,
                row_label=seat.row_label,
                seat_number=seat.seat_number,
                price_uah=seat.price_uah,
                state="blocked" if seat.is_blocked else occupied.get(seat.id, "available"),
            )
            for seat in seats
        ],
    )
