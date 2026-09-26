"""Public routing table. Anything not listed here is not reachable from outside,
including every /internal/* endpoint of the services."""

from dataclasses import dataclass

API_PREFIX = "/api/v1"


@dataclass(frozen=True)
class Route:
    prefix: str
    upstream: str
    requires_auth: bool


ROUTES: tuple[Route, ...] = (
    Route(f"{API_PREFIX}/auth", "identity", requires_auth=False),
    Route(f"{API_PREFIX}/me", "identity", requires_auth=True),
    Route(f"{API_PREFIX}/events", "catalog", requires_auth=False),
    Route(f"{API_PREFIX}/sessions", "catalog", requires_auth=False),
    Route(f"{API_PREFIX}/bookings", "booking", requires_auth=True),
)


def match_route(path: str) -> Route | None:
    # Dot segments could climb out of a public prefix into /internal/*.
    if any(segment in (".", "..") for segment in path.split("/")):
        return None
    for route in ROUTES:
        if path == route.prefix or path.startswith(route.prefix + "/"):
            return route
    return None
