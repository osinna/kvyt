import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SeatState = Literal["available", "held", "sold", "blocked"]
EventStatus = Literal["draft", "published", "archived"]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    venue: str
    city: str
    description: str
    organizer_id: uuid.UUID
    status: str


class CreateEventRequest(BaseModel):
    """A new event always starts as a draft of the caller."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    venue: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)


class UpdateEventRequest(BaseModel):
    """Partial update: only the fields present in the body change."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: EventStatus | None = None

    @field_validator("title", "description", "status")
    @classmethod
    def _not_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class EventPage(BaseModel):
    items: list[EventOut]
    total: int
    limit: int
    offset: int


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    starts_at: datetime
    base_price_uah: int


class SeatOut(BaseModel):
    id: uuid.UUID
    row_label: str
    seat_number: int
    price_uah: int
    state: SeatState


class SessionSeats(BaseModel):
    session_id: uuid.UUID
    seats: list[SeatOut]


class InternalSeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    row_label: str
    seat_number: int
    price_uah: int
    is_blocked: bool


class InternalSessionSeats(BaseModel):
    session_id: uuid.UUID
    starts_at: datetime
    event_status: str
    seats: list[InternalSeatOut]


class InternalEventOut(BaseModel):
    id: uuid.UUID
    organizer_id: uuid.UUID
    session_ids: list[uuid.UUID]


class InternalSessionSummary(BaseModel):
    session_id: uuid.UUID
    total_seats: int
    blocked_seats: int
