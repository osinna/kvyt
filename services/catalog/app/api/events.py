import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import EVENT_PUBLISHED, Event, Session
from ..queries import get_public_event
from ..schemas import EventOut, EventPage, SessionOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventPage)
async def list_events(
    city: str | None = Query(default=None, max_length=100),
    status: Literal["published", "archived"] = EVENT_PUBLISHED,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> EventPage:
    conditions = [Event.status == status]
    if city:
        conditions.append(func.lower(Event.city) == city.strip().lower())

    total = await db.scalar(select(func.count()).select_from(Event).where(*conditions))
    events = await db.scalars(
        select(Event).where(*conditions).order_by(Event.title, Event.id).limit(limit).offset(offset)
    )
    return EventPage(
        items=[EventOut.model_validate(e) for e in events],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_session)) -> Event:
    return await get_public_event(db, event_id)


@router.get("/{event_id}/sessions", response_model=list[SessionOut])
async def list_event_sessions(
    event_id: uuid.UUID, db: AsyncSession = Depends(get_session)
) -> list[Session]:
    await get_public_event(db, event_id)
    sessions = await db.scalars(
        select(Session).where(Session.event_id == event_id).order_by(Session.starts_at, Session.id)
    )
    return list(sessions)
