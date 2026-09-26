from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import DomainError
from kvyt_common.auth import ROLE_USER

from ..config import get_settings
from ..db import get_session
from ..models import RefreshToken, User
from ..schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from ..security import (
    hash_password,
    hash_refresh_token,
    issue_access_token,
    new_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _invalid_refresh() -> DomainError:
    return DomainError("invalid_refresh_token", "Refresh token is invalid or already used", 401)


async def _issue_pair(session: AsyncSession, user: User) -> TokenPair:
    settings = get_settings()
    token, token_hash = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    await session.commit()
    return TokenPair(
        access_token=issue_access_token(user.id, user.role),
        refresh_token=token,
        expires_in=settings.access_token_ttl_seconds,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)) -> User:
    user = User(
        email=body.email,
        password_hash=await run_in_threadpool(hash_password, body.password),
        full_name=body.full_name,
        role=ROLE_USER,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise DomainError("email_already_registered", "Email is already registered", 409)
    return user


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    user = await session.scalar(select(User).where(User.email == body.email))
    password_hash = user.password_hash if user else None
    if not await run_in_threadpool(verify_password, body.password, password_hash):
        raise DomainError("invalid_credentials", "Email or password is incorrect", 401)
    return await _issue_pair(session, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    now = datetime.now(timezone.utc)
    stored = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(body.refresh_token))
        .with_for_update()
    )
    if stored is None or stored.used_at is not None or stored.expires_at <= now:
        raise _invalid_refresh()
    user = await session.get(User, stored.user_id)
    if user is None:
        raise _invalid_refresh()
    stored.used_at = now
    return await _issue_pair(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> Response:
    stored = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(body.refresh_token))
        .with_for_update()
    )
    # Idempotent: an unknown or already revoked token is not an error.
    if stored is not None and stored.used_at is None:
        stored.used_at = datetime.now(timezone.utc)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
