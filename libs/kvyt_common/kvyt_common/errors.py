import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .middleware import TRACE_ID_HEADER, current_trace_id


class DomainError(Exception):
    """Raised by business logic. Serialised into the shared error envelope."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"{code}: {message}")


_STATUS_TO_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    415: "unsupported_media_type",
    422: "unprocessable_entity",
    429: "too_many_requests",
    503: "service_unavailable",
}


def _envelope(code: str, message: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "trace_id": current_trace_id(),
        }
    }


def _headers() -> dict[str, str]:
    trace_id = current_trace_id()
    return {TRACE_ID_HEADER: trace_id} if trace_id else {}


def register_exception_handlers(app: FastAPI) -> None:
    error_log = logging.getLogger("kvyt.error")

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message),
            headers=_headers(),
        )

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, "error")
        detail = exc.detail if isinstance(exc.detail, str) else code
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, detail),
            headers=_headers(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope("unprocessable_entity", "Request validation failed"),
            headers=_headers(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        error_log.exception("unhandled exception")
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error", "Internal server error"),
            headers=_headers(),
        )
