"""JWT verification and caller identity.

Gateway verifies the access token and forwards the caller as X-User-Id /
X-User-Role headers. Internal services trust those headers for *who* the
caller is and decide on their own what the caller may do.
"""

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Request

from .errors import DomainError


JWT_ALGORITHM = "HS256"

USER_ID_HEADER = "X-User-Id"
USER_ROLE_HEADER = "X-User-Role"

ROLE_GUEST = "guest"
ROLE_USER = "user"
ROLE_ORGANIZER = "organizer"
ROLE_ADMIN = "admin"
STORED_ROLES = (ROLE_USER, ROLE_ORGANIZER, ROLE_ADMIN)


@dataclass(frozen=True)
class Caller:
    user_id: uuid.UUID | None
    role: str

    @property
    def is_guest(self) -> bool:
        return self.user_id is None


def decode_access_token(token: str, secret: str) -> dict:
    """Returns claims of a valid access token, raises DomainError(401) otherwise."""
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "role", "exp", "iat", "jti"]},
        )
    except jwt.ExpiredSignatureError:
        raise DomainError("token_expired", "Access token has expired", 401)
    except jwt.PyJWTError:
        raise DomainError("invalid_token", "Access token is invalid", 401)


def get_caller(request: Request) -> Caller:
    """FastAPI dependency: caller as forwarded by gateway. Guest if absent."""
    raw_id = request.headers.get(USER_ID_HEADER)
    if not raw_id:
        return Caller(user_id=None, role=ROLE_GUEST)
    try:
        user_id = uuid.UUID(raw_id)
    except ValueError:
        raise DomainError("invalid_token", "Caller identity is malformed", 401)
    return Caller(user_id=user_id, role=request.headers.get(USER_ROLE_HEADER, ROLE_USER))


def require_user(request: Request) -> Caller:
    """FastAPI dependency: authenticated caller, 401 for guests."""
    caller = get_caller(request)
    if caller.is_guest:
        raise DomainError("unauthorized", "Authentication required", 401)
    return caller
