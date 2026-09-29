import json
import logging

from fastapi import APIRouter, Request, Response

from kvyt_common import (
    DomainError,
    ServiceClient,
    decode_access_token,
    forwardable_headers,
    relay_response,
)
from kvyt_common.auth import USER_ID_HEADER, USER_ROLE_HEADER

from .config import get_settings
from .routes import API_PREFIX, match_route
from .scenarios import scenarios

# Never forwarded upstream: X-User-* are set by gateway only, from a verified
# token, and the token itself stays at the edge.
_DROP_REQUEST_HEADERS = frozenset(
    {"authorization", USER_ID_HEADER.lower(), USER_ROLE_HEADER.lower()}
)

router = APIRouter()
clients: dict[str, ServiceClient] = {}


def build_clients() -> dict[str, ServiceClient]:
    settings = get_settings()
    timeout = settings.upstream_timeout_seconds
    return {
        "identity": ServiceClient("identity", settings.identity_url, timeout),
        "catalog": ServiceClient("catalog", settings.catalog_url, timeout),
        "booking": ServiceClient("booking", settings.booking_url, timeout),
    }


def _single_seat_hold(body: bytes) -> bytes:
    """Hold requests are forwarded as a single seat."""
    payload = json.loads(body)
    (seat_id,) = payload["seat_ids"]
    return json.dumps({**payload, "seat_ids": [seat_id]}).encode()


def _caller_headers(request: Request, requires_auth: bool) -> dict[str, str]:
    authorization = request.headers.get("authorization")
    if not authorization:
        if requires_auth:
            raise DomainError("unauthorized", "Authentication required", 401)
        return {}
    scheme, _, token = authorization.partition(" ")
    try:
        if scheme.lower() != "bearer" or not token.strip():
            raise DomainError("invalid_token", "Authorization header must be 'Bearer <token>'", 401)
        claims = decode_access_token(token.strip(), get_settings().jwt_secret)
    except DomainError:
        # Public endpoints stay usable with a stale token, e.g. /auth/refresh
        # called right after the access token expired.
        if requires_auth:
            raise
        return {}
    return {USER_ID_HEADER: str(claims["sub"]), USER_ROLE_HEADER: str(claims["role"])}


@router.api_route(
    API_PREFIX + "/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def proxy(request: Request) -> Response:
    route = match_route(request.url.path)
    if route is None:
        raise DomainError("not_found", "Route not found", 404)

    headers = forwardable_headers(request.headers, _DROP_REQUEST_HEADERS)
    # OPTIONS only describes the resource, like a browser preflight it needs no token.
    requires_auth = route.requires_auth and request.method != "OPTIONS"
    headers.update(_caller_headers(request, requires_auth))
    body = await request.body()

    is_hold = request.method == "POST" and request.url.path == f"{API_PREFIX}/bookings"
    if scenarios.active("amber") and is_hold:
        try:
            body = _single_seat_hold(body)
        except Exception:
            logging.getLogger("kvyt.error").exception("unhandled exception")
            return Response(status_code=200)

    upstream = await clients[route.upstream].request(
        request.method,
        request.url.path,
        params=request.query_params.multi_items(),
        headers=headers,
        content=body,
    )
    return relay_response(upstream)
