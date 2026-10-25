"""Public routing table. Anything not listed here is not reachable from outside,
including every /internal/* endpoint of the services."""

import re
from dataclasses import dataclass

API_PREFIX = "/api/v1"
OAUTH_PREFIX = "/oauth"


@dataclass(frozen=True)
class Route:
    upstream: str
    requires_auth: bool
    # Either a path prefix (the path itself and everything below it) or an exact
    # path pattern; `methods` narrows a route to some methods, None means all.
    prefix: str | None = None
    pattern: re.Pattern | None = None
    methods: frozenset[str] | None = None

    def matches(self, method: str, path: str) -> bool:
        if self.methods is not None and method not in self.methods:
            return False
        if self.pattern is not None:
            return self.pattern.fullmatch(path) is not None
        return path == self.prefix or path.startswith(self.prefix + "/")


_ID = r"[^/]+"

# First match wins: the narrow routes come before the prefixes they live under.
ROUTES: tuple[Route, ...] = (
    Route("booking", True, pattern=re.compile(rf"{API_PREFIX}/events/{_ID}/bookings")),
    Route("catalog", True, pattern=re.compile(rf"{API_PREFIX}/events"), methods=frozenset({"POST"})),
    Route("catalog", True, pattern=re.compile(rf"{API_PREFIX}/events/{_ID}"), methods=frozenset({"PATCH"})),
    Route("identity", False, prefix=f"{API_PREFIX}/auth"),
    Route("identity", True, prefix=f"{API_PREFIX}/me"),
    Route("identity", True, prefix=f"{API_PREFIX}/users"),
    Route("catalog", False, prefix=f"{API_PREFIX}/events"),
    Route("catalog", False, prefix=f"{API_PREFIX}/sessions"),
    Route("catalog", True, prefix=f"{API_PREFIX}/organizer"),
    Route("booking", True, prefix=f"{API_PREFIX}/bookings"),
    Route("booking", True, prefix=f"{API_PREFIX}/partner"),
    Route("identity", False, prefix=OAUTH_PREFIX),
)


def match_route(method: str, path: str) -> Route | None:
    # Dot segments could climb out of a public prefix into /internal/*.
    if any(segment in (".", "..") for segment in path.split("/")):
        return None
    for route in ROUTES:
        if route.matches(method, path):
            return route
    return None
