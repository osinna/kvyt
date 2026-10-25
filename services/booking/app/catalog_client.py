import uuid
from dataclasses import dataclass
from datetime import datetime

from kvyt_common import DomainError, ServiceClient

from .config import get_settings


@dataclass(frozen=True)
class CatalogSeat:
    id: uuid.UUID
    row_label: str
    seat_number: int
    price_uah: int
    is_blocked: bool


@dataclass(frozen=True)
class CatalogSession:
    id: uuid.UUID
    starts_at: datetime
    event_status: str
    seats: dict[uuid.UUID, CatalogSeat]


@dataclass(frozen=True)
class CatalogEvent:
    id: uuid.UUID
    organizer_id: uuid.UUID
    session_ids: list[uuid.UUID]


_client: ServiceClient | None = None


def open_client() -> None:
    global _client
    _client = ServiceClient("catalog", get_settings().catalog_url)


async def close_client() -> None:
    if _client is not None:
        await _client.aclose()


async def fetch_session_seats(session_id: uuid.UUID, seat_ids: list[uuid.UUID]) -> CatalogSession:
    """Seats of the session among seat_ids. Unknown or foreign ids are absent."""
    assert _client is not None, "catalog client is not open"
    response = await _client.get(
        "/internal/seats",
        params={"session_id": str(session_id), "ids": ",".join(str(s) for s in seat_ids)},
    )
    if response.status_code == 404:
        raise DomainError("session_not_found", "Session not found", 404)
    if response.status_code != 200:
        raise DomainError("upstream_error", "Catalog returned an unexpected response", 502)
    body = response.json()
    return CatalogSession(
        id=uuid.UUID(body["session_id"]),
        starts_at=datetime.fromisoformat(body["starts_at"]),
        event_status=body["event_status"],
        seats={
            uuid.UUID(s["id"]): CatalogSeat(
                id=uuid.UUID(s["id"]),
                row_label=s["row_label"],
                seat_number=s["seat_number"],
                price_uah=s["price_uah"],
                is_blocked=s["is_blocked"],
            )
            for s in body["seats"]
        },
    )


async def fetch_event(event_id: uuid.UUID) -> CatalogEvent:
    """Organizer and sessions of an event in any status."""
    assert _client is not None, "catalog client is not open"
    response = await _client.get(f"/internal/events/{event_id}")
    if response.status_code == 404:
        raise DomainError("event_not_found", "Event not found", 404)
    if response.status_code != 200:
        raise DomainError("upstream_error", "Catalog returned an unexpected response", 502)
    body = response.json()
    return CatalogEvent(
        id=uuid.UUID(body["id"]),
        organizer_id=uuid.UUID(body["organizer_id"]),
        session_ids=[uuid.UUID(s) for s in body["session_ids"]],
    )


async def fetch_session_summary(session_id: uuid.UUID) -> tuple[int, int]:
    """(total seats, blocked seats) of a public session."""
    assert _client is not None, "catalog client is not open"
    response = await _client.get(f"/internal/sessions/{session_id}/summary")
    if response.status_code == 404:
        raise DomainError("session_not_found", "Session not found", 404)
    if response.status_code != 200:
        raise DomainError("upstream_error", "Catalog returned an unexpected response", 502)
    body = response.json()
    return body["total_seats"], body["blocked_seats"]
