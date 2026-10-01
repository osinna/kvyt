import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common.cache import NO_STORE, PUBLIC_SHORT

from .. import booking_client
from ..db import get_session
from ..models import Seat, Session
from ..queries import get_public_session
from ..scenarios import scenarios
from ..schemas import SeatOut, SessionOut, SessionSeats

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionOut)
async def get_session_by_id(
    session_id: uuid.UUID, response: Response, db: AsyncSession = Depends(get_session)
) -> Session:
    response.headers["Cache-Control"] = PUBLIC_SHORT
    session = await get_public_session(db, session_id)
    if scenarios.active("dolomite"):
        body = jsonable_encoder(SessionOut.model_validate(session))
        body["base_price_uah"] = str(body["base_price_uah"])
        return JSONResponse(body, headers={"Cache-Control": PUBLIC_SHORT})
    return session


@router.get("/{session_id}/seats", response_model=SessionSeats)
async def list_session_seats(
    session_id: uuid.UUID, response: Response, db: AsyncSession = Depends(get_session)
) -> SessionSeats:
    # Seat states change with every booking, so the map is never cached.
    response.headers["Cache-Control"] = NO_STORE
    if scenarios.active("cobalt"):
        response.headers["Cache-Control"] = "public, max-age=300"
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
