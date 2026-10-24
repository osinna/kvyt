from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import Caller, require_role
from kvyt_common.auth import ROLE_ADMIN, ROLE_ORGANIZER

from ..db import get_session
from ..models import Event
from ..schemas import EventOut

router = APIRouter(prefix="/organizer", tags=["organizer"])


@router.get("/events", response_model=list[EventOut])
async def list_managed_events(
    caller: Caller = Depends(require_role(ROLE_ORGANIZER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_session),
) -> list[Event]:
    """Every event the caller manages, drafts included: own for organizer, all for admin."""
    query = select(Event).order_by(Event.title, Event.id)
    if caller.role != ROLE_ADMIN:
        query = query.where(Event.organizer_id == caller.user_id)
    return list(await db.scalars(query))
