import logging
import time
import uuid
from contextvars import ContextVar
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


TRACE_ID_HEADER = "X-Trace-Id"

_trace_id_var: ContextVar[str | None] = ContextVar("kvyt_trace_id", default=None)


def current_trace_id() -> str | None:
    return _trace_id_var.get()


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get()
        return True


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Assigns a trace id to every request, propagates it in logs and response headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = request.headers.get(TRACE_ID_HEADER) or str(uuid.uuid4())
        token = _trace_id_var.set(trace_id)
        access_log = logging.getLogger("kvyt.http")
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            access_log.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": duration_ms,
                },
            )
            _trace_id_var.reset(token)
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[TRACE_ID_HEADER] = trace_id
        access_log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        _trace_id_var.reset(token)
        return response
