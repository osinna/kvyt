import re
import uuid
from datetime import datetime
from typing import Literal

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


class UpdateMeRequest(BaseModel):
    """Partial update: only the fields present in the body change."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _not_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("full_name cannot be null")
        return value


class Preferences(BaseModel):
    """Full representation. PUT replaces it; a field left out falls back to its default."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    language: Literal["uk", "en"] = "uk"
    newsletter: bool = False


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
