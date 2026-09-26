import uuid
from typing import Literal

from kvyt_common import DomainError, ServiceClient

from .config import get_settings

OccupiedState = Literal["held", "sold"]

_client: ServiceClient | None = None


def open_client() -> None:
    global _client
    _client = ServiceClient("booking", get_settings().booking_url)


async def close_client() -> None:
    if _client is not None:
        await _client.aclose()


async def fetch_occupancy(session_id: uuid.UUID) -> dict[uuid.UUID, OccupiedState]:
    """Occupied seats of the session. Seats not in the result are free."""
    assert _client is not None, "booking client is not open"
    response = await _client.get("/internal/occupancy", params={"session_id": str(session_id)})
    if response.status_code != 200:
        raise DomainError("upstream_error", "Booking returned an unexpected response", 502)
    return {uuid.UUID(s["seat_id"]): s["state"] for s in response.json()["seats"]}
