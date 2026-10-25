import json
import logging
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from kvyt_common import (
    DomainError,
    ServiceClient,
    decode_access_token,
    forwardable_headers,
    relay_response,
)
from kvyt_common.auth import CLIENT_ID_HEADER, USER_ID_HEADER, USER_ROLE_HEADER

from .config import get_settings
from .login_limit import LoginLimiter
from .routes import API_PREFIX, OAUTH_PREFIX, match_route
from .scenarios import scenarios
from .scopes import check_scope

# Never forwarded upstream: X-User-* and X-Client-Id are set by gateway only,
# from a verified token, and the token itself stays at the edge. /oauth/token
# is the exception for Authorization: there it carries client credentials.
_IDENTITY_HEADERS = frozenset(
    {USER_ID_HEADER.lower(), USER_ROLE_HEADER.lower(), CLIENT_ID_HEADER.lower()}
)
_DROP_REQUEST_HEADERS = _IDENTITY_HEADERS | {"authorization"}
_OAUTH_TOKEN_PATH = f"{OAUTH_PREFIX}/token"
_OAUTH_AUTHORIZE_PATH = f"{OAUTH_PREFIX}/authorize"

_TOO_MANY_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>KVYT · Too many attempts</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 420px; margin: 48px auto;">
<h1>Too many failed login attempts</h1>
<p>Try again in {seconds} seconds.</p>
</body></html>
"""

router = APIRouter()
clients: dict[str, ServiceClient] = {}
login_limiter = LoginLimiter()


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
    """Caller identity for the upstream service, from a verified token.

    A user token gives X-User-Id / X-User-Role. A client token (Client
    Credentials) has no user behind it and gives X-Client-Id only.
    """
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
    if requires_auth:
        check_scope(claims, request.method, request.url.path)
    if str(claims["sub"]).startswith("client:"):
        return {CLIENT_ID_HEADER: str(claims.get("client_id", ""))}
    return {USER_ID_HEADER: str(claims["sub"]), USER_ROLE_HEADER: str(claims["role"])}


@router.api_route(
    API_PREFIX + "/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
@router.api_route(
    OAUTH_PREFIX + "/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def proxy(request: Request) -> Response:
    path = request.url.path
    route = match_route(request.method, path)
    if route is None:
        raise DomainError("not_found", "Route not found", 404)

    drop = _IDENTITY_HEADERS if path == _OAUTH_TOKEN_PATH else _DROP_REQUEST_HEADERS
    headers = forwardable_headers(request.headers, drop)
    # OPTIONS only describes the resource, like a browser preflight it needs no token.
    requires_auth = route.requires_auth and request.method != "OPTIONS"
    headers.update(_caller_headers(request, requires_auth))
    body = await request.body()

    is_hold = request.method == "POST" and path == f"{API_PREFIX}/bookings"
    if scenarios.active("amber") and is_hold:
        try:
            body = _single_seat_hold(body)
        except Exception:
            logging.getLogger("kvyt.error").exception("unhandled exception")
            return Response(status_code=200)

    limit_key = None
    client_ip = request.client.host if request.client else ""
    is_login = request.method == "POST" and path == f"{API_PREFIX}/auth/login"
    is_consent = request.method == "POST" and path == _OAUTH_AUTHORIZE_PATH
    if (is_login or is_consent) and not scenarios.active("jasper"):
        if is_login:
            limit_key = LoginLimiter.key(body, client_ip)
        else:
            limit_key = LoginLimiter.form_key(body, client_ip)
    if limit_key is not None:
        try:
            login_limiter.check(limit_key)
        except DomainError as exc:
            if not is_consent:
                raise
            seconds = exc.headers["Retry-After"]
            return HTMLResponse(
                _TOO_MANY_PAGE.format(seconds=seconds),
                status_code=429,
                headers={"Retry-After": seconds},
            )

    upstream = await clients[route.upstream].request(
        request.method,
        request.url.path,
        params=request.query_params.multi_items(),
        headers=headers,
        content=body,
    )
    if limit_key is not None:
        if is_login:
            succeeded = upstream.status_code == 200
        else:
            # Only a redirect that carries a code means the password was right.
            location = urlsplit(upstream.headers.get("location", ""))
            succeeded = upstream.status_code == 302 and "code" in parse_qs(location.query)
        login_limiter.record(limit_key, upstream.status_code, succeeded)
    return relay_response(upstream)
