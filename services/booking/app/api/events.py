import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import Caller, DomainError, require_role
from kvyt_common.auth import ROLE_ADMIN, ROLE_ORGANIZER

from .. import catalog_client, lifecycle
from ..db import get_session
from ..models import Booking
from ..schemas import BookingOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/{event_id}/bookings", response_model=list[BookingOut])
async def list_event_bookings(
    event_id: uuid.UUID,
    caller: Caller = Depends(require_role(ROLE_ORGANIZER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_session),
) -> list[Booking]:
    """Bookings for every session of the event: any event for admin, own for organizer.

    Someone else's event is reported as missing, so its existence is not confirmed.
    """
    event = await catalog_client.fetch_event(event_id)
    if caller.role != ROLE_ADMIN and event.organizer_id != caller.user_id:
        raise DomainError("event_not_found", "Event not found", 404)
    if not event.session_ids:
        return []
    await lifecycle.expire_stale_holds(db, Booking.session_id.in_(event.session_ids))
    await db.commit()
    bookings = await db.scalars(
        select(Booking)
        .where(Booking.session_id.in_(event.session_ids))
        .order_by(Booking.created_at.desc(), Booking.id)
    )
    return list(bookings)
