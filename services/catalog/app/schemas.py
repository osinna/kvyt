import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SeatState = Literal["available", "held", "sold", "blocked"]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    venue: str
    city: str
    description: str
    organizer_id: uuid.UUID
    status: str


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
