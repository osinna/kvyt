from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import Caller, DomainError, require_user

from ..db import get_session
from ..models import User, UserPreferences
from ..schemas import Preferences, UpdateMeRequest, UserOut

router = APIRouter(tags=["me"])


async def _current_user(session: AsyncSession, caller: Caller) -> User:
    user = await session.get(User, caller.user_id)
    if user is None:
        raise DomainError("unauthorized", "User no longer exists", 401)
    return user


@router.get("/me", response_model=UserOut)
async def me(
    caller: Caller = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    return await _current_user(session, caller)


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UpdateMeRequest,
    caller: Caller = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await _current_user(session, caller)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/me/preferences", response_model=Preferences)
async def get_preferences(
    caller: Caller = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> Preferences:
    await _current_user(session, caller)
    stored = await session.get(UserPreferences, caller.user_id)
    return Preferences.model_validate(stored) if stored else Preferences()


@router.put("/me/preferences", response_model=Preferences)
async def replace_preferences(
    body: Preferences,
    caller: Caller = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> Preferences:
    await _current_user(session, caller)
    stored = await session.get(UserPreferences, caller.user_id)
    if stored is None:
        stored = UserPreferences(user_id=caller.user_id)
        session.add(stored)
    stored.language = body.language
    stored.newsletter = body.newsletter
    await session.commit()
    return body
