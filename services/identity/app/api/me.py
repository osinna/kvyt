from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import Caller, DomainError, require_user

from ..db import get_session
from ..models import User
from ..schemas import UserOut

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserOut)
async def me(
    caller: Caller = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(User, caller.user_id)
    if user is None:
        raise DomainError("unauthorized", "User no longer exists", 401)
    return user
