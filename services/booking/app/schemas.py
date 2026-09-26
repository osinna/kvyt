import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

MAX_SEATS_PER_BOOKING = 10


class CreateBookingRequest(BaseModel):
    session_id: uuid.UUID
    seat_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_SEATS_PER_BOOKING)

    @field_validator("seat_ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("seat_ids must not contain duplicates")
        return value


class BookingItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seat_id: uuid.UUID
    price_uah: int


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID
    status: str
    held_until: datetime
    created_at: datetime
    updated_at: datetime
    items: list[BookingItemOut]

    @computed_field
    @property
    def total_uah(self) -> int:
        return sum(item.price_uah for item in self.items)


class OccupiedSeat(BaseModel):
    seat_id: uuid.UUID
    state: Literal["held", "sold"]


class Occupancy(BaseModel):
    session_id: uuid.UUID
    seats: list[OccupiedSeat]
