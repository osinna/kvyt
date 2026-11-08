import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import Caller, require_user

from ..db import get_session
from ..models import Notification
from ..schemas import NotificationOut

router = APIRouter(tags=["notifications"])


@router.get("/me/notifications", response_model=list[NotificationOut])
async def list_my_notifications(
    booking_id: uuid.UUID | None = None,
    caller: Caller = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[Notification]:
    """Caller's own notifications, newest first. None yet is an empty list, not 404."""
    query = select(Notification).where(Notification.user_id == caller.user_id)
    if booking_id is not None:
        query = query.where(Notification.booking_id == booking_id)
    rows = await db.scalars(query.order_by(Notification.created_at.desc(), Notification.id))
    return list(rows)
