import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import Caller, DomainError
from kvyt_common.auth import ROLE_ADMIN

from .models import EVENT_ARCHIVED, EVENT_PUBLISHED, Event, Session

# Drafts are visible only to their organizer, through the organizer endpoints.
PUBLIC_EVENT_STATUSES = (EVENT_PUBLISHED, EVENT_ARCHIVED)


def _event_not_found() -> DomainError:
    return DomainError("event_not_found", "Event not found", 404)


async def get_public_event(db: AsyncSession, event_id: uuid.UUID) -> Event:
    event = await db.get(Event, event_id)
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        raise _event_not_found()
    return event


async def get_managed_event(db: AsyncSession, event_id: uuid.UUID, caller: Caller) -> Event:
    """Event the caller may manage: any for admin, own for organizer.

    Someone else's event is reported as missing, so its existence is not confirmed.
    """
    event = await db.get(Event, event_id)
    if event is None or (caller.role != ROLE_ADMIN and event.organizer_id != caller.user_id):
        raise _event_not_found()
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
