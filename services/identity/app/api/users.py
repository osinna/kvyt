import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import Caller, DomainError, require_role
from kvyt_common.auth import ROLE_ADMIN

from ..db import get_session
from ..models import User
from ..schemas import UpdateRoleRequest, UserOut

router = APIRouter(prefix="/users", tags=["users"])

require_admin = require_role(ROLE_ADMIN)


@router.get("", response_model=list[UserOut])
async def list_users(
    _: Caller = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[User]:
    users = await session.scalars(select(User).order_by(User.email))
    return list(users)


@router.patch("/{user_id}", response_model=UserOut)
async def update_role(
    user_id: uuid.UUID,
    body: UpdateRoleRequest,
    _: Caller = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> User:
    """The new role reaches the user's next access token; the current one keeps its claims."""
    user = await session.get(User, user_id)
    if user is None:
        raise DomainError("user_not_found", "User not found", 404)
    user.role = body.role
    await session.commit()
    await session.refresh(user)
    return user
