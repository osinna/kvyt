"""Cache-Control policy. Every response states whether it may be cached."""

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Personal or fast-changing data.
NO_STORE = "no-store"
# Unversioned static assets: may be stored, must be revalidated.
REVALIDATE = "no-cache"
# Public reference data that tolerates a minute of staleness.
PUBLIC_SHORT = "public, max-age=60"


class DefaultCacheControlMiddleware(BaseHTTPMiddleware):
    """Marks any response without an explicit policy as not cacheable."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", NO_STORE)
        return response
