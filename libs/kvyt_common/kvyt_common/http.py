"""HTTP client for calls to other KVYT services.

Every outgoing call carries the current trace id and produces one log line
with target, method, path, status and duration_ms.
"""

import logging
import time

import httpx
from starlette.responses import Response

from .errors import DomainError
from .middleware import TRACE_ID_HEADER, current_trace_id


# Connection-level headers that must not be relayed by a proxy, plus headers the
# relaying side recomputes itself.
HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "proxy-authorization",
        "host",
        "content-length",
        "content-encoding",
        "x-trace-id",
    }
)


def forwardable_headers(headers, drop: frozenset[str] = frozenset()) -> dict[str, str]:
    skip = HOP_BY_HOP_HEADERS | drop
    return {name: value for name, value in headers.items() if name.lower() not in skip}


def relay_response(upstream: httpx.Response) -> Response:
    """Passes an upstream response to the client unchanged, headers included."""
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=forwardable_headers(upstream.headers),
    )


class ServiceClient:
    def __init__(self, target: str, base_url: str, timeout: float = 5.0) -> None:
        self.target = target
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._log = logging.getLogger("kvyt.outgoing")

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = httpx.Headers(kwargs.pop("headers", None))
        trace_id = current_trace_id()
        if trace_id:
            headers[TRACE_ID_HEADER] = trace_id
        started = time.perf_counter()
        extra = {"target": self.target, "method": method, "path": path}
        try:
            response = await self._client.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException:
            self._log.warning("outgoing request timed out", extra=self._timed(extra, started))
            raise DomainError("upstream_timeout", "Upstream service did not respond in time", 504)
        except httpx.TransportError:
            self._log.warning("outgoing request failed", extra=self._timed(extra, started))
            raise DomainError("upstream_unavailable", "Upstream service is unavailable", 503)
        self._log.info(
            "outgoing request",
            extra=self._timed({**extra, "status": response.status_code}, started),
        )
        return response

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _timed(extra: dict, started: float) -> dict:
        return {**extra, "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
