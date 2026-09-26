from fastapi import APIRouter, Request, Response

from kvyt_common import DomainError, ServiceClient, decode_access_token
from kvyt_common.auth import USER_ID_HEADER, USER_ROLE_HEADER

from .config import get_settings
from .routes import API_PREFIX, match_route

# Never forwarded upstream. X-User-* are set by gateway only, from a verified
# token; X-Trace-Id is set by ServiceClient.
_DROP_REQUEST_HEADERS = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "proxy-authorization",
    "authorization",
    "x-trace-id",
    USER_ID_HEADER.lower(),
    USER_ROLE_HEADER.lower(),
}
_DROP_RESPONSE_HEADERS = {
    "content-length",
    "content-encoding",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "x-trace-id",
}

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
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def proxy(request: Request) -> Response:
    route = match_route(request.url.path)
    if route is None:
        raise DomainError("not_found", "Route not found", 404)

    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in _DROP_REQUEST_HEADERS
    }
    headers.update(_caller_headers(request, route.requires_auth))

    upstream = await clients[route.upstream].request(
        request.method,
        request.url.path,
        params=request.query_params.multi_items(),
        headers=headers,
        content=await request.body(),
    )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            name: value
            for name, value in upstream.headers.items()
            if name.lower() not in _DROP_RESPONSE_HEADERS
        },
    )
