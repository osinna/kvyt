import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import Caller, require_role
from kvyt_common.auth import ROLE_ADMIN, ROLE_ORGANIZER
from kvyt_common.cache import PUBLIC_SHORT

from ..db import get_session
from ..models import EVENT_DRAFT, EVENT_PUBLISHED, Event, Session
from ..queries import get_managed_event, get_public_event
from ..scenarios import scenarios
from ..schemas import CreateEventRequest, EventOut, EventPage, SessionOut, UpdateEventRequest

router = APIRouter(prefix="/events", tags=["events"])

require_manager = require_role(ROLE_ORGANIZER, ROLE_ADMIN)


@router.get("", response_model=EventPage)
async def list_events(
    response: Response,
    city: str | None = Query(default=None, max_length=100),
    status: Literal["published", "archived"] = EVENT_PUBLISHED,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> EventPage:
    response.headers["Cache-Control"] = PUBLIC_SHORT
    conditions = [Event.status == status]
    if city:
        conditions.append(func.lower(Event.city) == city.strip().lower())

    skip = offset
    if scenarios.active("emerald") and offset > 0:
        skip = offset + 1
    total = await db.scalar(select(func.count()).select_from(Event).where(*conditions))
    events = await db.scalars(
        select(Event).where(*conditions).order_by(Event.title, Event.id).limit(limit).offset(skip)
    )
    return EventPage(
        items=[EventOut.model_validate(e) for e in events],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=http_status.HTTP_201_CREATED, response_model=EventOut)
async def create_event(
    body: CreateEventRequest,
    caller: Caller = Depends(require_manager),
    db: AsyncSession = Depends(get_session),
) -> Event:
    event = Event(**body.model_dump(), organizer_id=caller.user_id, status=EVENT_DRAFT)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: uuid.UUID,
    body: UpdateEventRequest,
    caller: Caller = Depends(require_manager),
    db: AsyncSession = Depends(get_session),
) -> Event:
    event = await get_managed_event(db, event_id, caller)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("/{event_id}", response_model=EventOut)
async def get_event(
    event_id: uuid.UUID, response: Response, db: AsyncSession = Depends(get_session)
) -> Event:
    response.headers["Cache-Control"] = PUBLIC_SHORT
    return await get_public_event(db, event_id)


@router.get("/{event_id}/sessions", response_model=list[SessionOut])
async def list_event_sessions(
    event_id: uuid.UUID, response: Response, db: AsyncSession = Depends(get_session)
) -> list[Session]:
    response.headers["Cache-Control"] = PUBLIC_SHORT
    await get_public_event(db, event_id)
    sessions = await db.scalars(
        select(Session).where(Session.event_id == event_id).order_by(Session.starts_at, Session.id)
    )
    if scenarios.active("dolomite"):
        body = jsonable_encoder([SessionOut.model_validate(s) for s in sessions])
        for item in body:
            item["base_price_uah"] = str(item["base_price_uah"])
        return JSONResponse(body, headers={"Cache-Control": PUBLIC_SHORT})
    return list(sessions)
