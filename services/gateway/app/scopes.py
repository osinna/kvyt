"""Which OAuth scope opens which route.

Tokens from /auth/login carry no `scope` claim and keep full access, except for
partner routes. A token with `scope` (issued by /oauth/token) reaches only the
routes its scopes list; every other authenticated route needs the user's own
login. Scopes only narrow access: role and ownership checks in the services
stay as they are.
"""

import re

from kvyt_common import DomainError

from .routes import API_PREFIX

PARTNER_PREFIX = f"{API_PREFIX}/partner"

_ID = r"[^/]+"
_GET = frozenset({"GET", "HEAD"})

# (methods, exact path pattern, scope)
SCOPE_RULES: tuple[tuple[frozenset[str], re.Pattern, str], ...] = (
    (_GET, re.compile(rf"{API_PREFIX}/me"), "profile:read"),
    (_GET, re.compile(rf"{API_PREFIX}/bookings(/{_ID})?"), "bookings:read"),
    (frozenset({"POST"}), re.compile(rf"{API_PREFIX}/bookings"), "bookings:write"),
    (frozenset({"POST"}), re.compile(rf"{API_PREFIX}/bookings/{_ID}/(confirm|cancel)"), "bookings:write"),
    (frozenset({"DELETE"}), re.compile(rf"{API_PREFIX}/bookings/{_ID}"), "bookings:write"),
    (_GET, re.compile(rf"{PARTNER_PREFIX}/occupancy"), "occupancy:read"),
)


def required_scope(method: str, path: str) -> str | None:
    for methods, pattern, scope in SCOPE_RULES:
        if method in methods and pattern.fullmatch(path):
            return scope
    return None


def _insufficient(message: str) -> DomainError:
    return DomainError("insufficient_scope", message, 403)


def check_scope(claims: dict, method: str, path: str) -> None:
    """Raises 403 insufficient_scope when the token may not reach an authenticated route."""
    is_partner = path == PARTNER_PREFIX or path.startswith(PARTNER_PREFIX + "/")
    if "scope" not in claims:
        if is_partner:
            raise _insufficient("Partner endpoints need an OAuth token of a partner client")
        return
    needed = required_scope(method, path)
    if needed is None:
        raise _insufficient("This endpoint is not available to OAuth tokens, log in to KVYT directly")
    if needed not in str(claims["scope"]).split():
        raise _insufficient(f"The token lacks the '{needed}' scope")
