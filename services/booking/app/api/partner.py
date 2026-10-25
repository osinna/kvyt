"""Endpoints for partner services, reached with a Client Credentials token.

Gateway lets only tokens with the `occupancy:read` scope through and forwards
the client as X-Client-Id; a request without it did not come from a partner.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import DomainError
from kvyt_common.auth import CLIENT_ID_HEADER

from .. import catalog_client, lifecycle
from ..db import get_session
from ..models import Booking, BookingItem
from ..schemas import SessionOccupancy

router = APIRouter(prefix="/partner", tags=["partner"])


def require_client(request: Request) -> str:
    client_id = request.headers.get(CLIENT_ID_HEADER)
    if not client_id:
        raise DomainError("insufficient_scope", "Partner endpoints need an OAuth token of a partner client", 403)
    return client_id


@router.get("/occupancy", response_model=SessionOccupancy)
async def session_occupancy(
    session_id: uuid.UUID,
    _: str = Depends(require_client),
    db: AsyncSession = Depends(get_session),
) -> SessionOccupancy:
    """Seats taken by bookings (HELD, CONFIRMED or USED) and seats still free."""
    total, blocked = await catalog_client.fetch_session_summary(session_id)
    await lifecycle.expire_stale_holds(db, Booking.session_id == session_id)
    await db.commit()
    occupied = await db.scalar(
        select(func.count())
        .select_from(BookingItem)
        .join(Booking, Booking.id == BookingItem.booking_id)
        .where(Booking.session_id == session_id, BookingItem.is_active)
    )
    return SessionOccupancy(
        session_id=session_id,
        total_seats=total,
        blocked_seats=blocked,
        occupied_seats=occupied or 0,
        available_seats=total - blocked - (occupied or 0),
    )
