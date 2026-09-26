"""Endpoints for other services. Not routed by gateway."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import DomainError

from ..db import get_session
from ..models import Event, Seat, Session
from ..schemas import InternalSeatOut, InternalSessionSeats

router = APIRouter(prefix="/internal", tags=["internal"])

MAX_IDS = 100


def _parse_ids(raw: str) -> list[uuid.UUID]:
    try:
        ids = [uuid.UUID(item) for item in raw.split(",") if item.strip()]
    except ValueError:
        raise DomainError("invalid_seat_ids", "ids must be a comma-separated list of UUIDs", 422)
    if not ids or len(ids) > MAX_IDS:
        raise DomainError("invalid_seat_ids", f"ids must contain 1 to {MAX_IDS} UUIDs", 422)
    return ids


@router.get("/seats", response_model=InternalSessionSeats)
async def seats_of_session(
    session_id: uuid.UUID,
    ids: str = Query(max_length=MAX_IDS * 37),
    db: AsyncSession = Depends(get_session),
) -> InternalSessionSeats:
    """Returns only the requested seats that exist and belong to the session.

    The caller detects unknown or foreign seat ids by comparing counts.
    """
    seat_ids = _parse_ids(ids)
    row = (
        await db.execute(
            select(Session, Event.status)
            .join(Event, Event.id == Session.event_id)
            .where(Session.id == session_id)
        )
    ).one_or_none()
    if row is None:
        raise DomainError("session_not_found", "Session not found", 404)
    session, event_status = row

    seats = await db.scalars(
        select(Seat)
        .where(Seat.session_id == session_id, Seat.id.in_(seat_ids))
        .order_by(Seat.row_label, Seat.seat_number)
    )
    return InternalSessionSeats(
        session_id=session.id,
        starts_at=session.starts_at,
        event_status=event_status,
        seats=[InternalSeatOut.model_validate(s) for s in seats],
    )
