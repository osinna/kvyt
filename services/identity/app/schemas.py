import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Deliberately permissive: internal domains such as *.local must be accepted.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("invalid email address")
    return value


class RegisterRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=200)

    _email = field_validator("email")(_normalize_email)


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=72)

    _email = field_validator("email")(_normalize_email)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
