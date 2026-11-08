"""Booking events for other services. Published only after the change is committed."""

from kvyt_common.events import BOOKING_CANCELLED, BOOKING_CONFIRMED, EventPublisher

from .config import get_settings
from .models import Booking

publisher = EventPublisher(get_settings().broker_url)


async def _publish(event: str, booking: Booking) -> None:
    await publisher.publish(
        event,
        {
            "booking_id": str(booking.id),
            "user_id": str(booking.user_id),
            "session_id": str(booking.session_id),
            "seat_ids": [str(item.seat_id) for item in booking.items],
        },
    )


async def booking_confirmed(booking: Booking) -> None:
    await _publish(BOOKING_CONFIRMED, booking)


async def booking_cancelled(booking: Booking) -> None:
    await _publish(BOOKING_CANCELLED, booking)
