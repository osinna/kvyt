import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import DomainError

from .models import EVENT_ARCHIVED, EVENT_PUBLISHED, Event, Session

# Drafts are visible only to their organizer; organizer access arrives with
# role-based permissions, so for now drafts are not visible publicly at all.
PUBLIC_EVENT_STATUSES = (EVENT_PUBLISHED, EVENT_ARCHIVED)


async def get_public_event(db: AsyncSession, event_id: uuid.UUID) -> Event:
    event = await db.get(Event, event_id)
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        raise DomainError("event_not_found", "Event not found", 404)
    return event


async def get_public_session(db: AsyncSession, session_id: uuid.UUID) -> Session:
    row = await db.scalar(
        select(Session)
        .join(Event, Event.id == Session.event_id)
        .where(Session.id == session_id, Event.status.in_(PUBLIC_EVENT_STATUSES))
    )
    if row is None:
        raise DomainError("session_not_found", "Session not found", 404)
    return row
