import json
import logging
import sys
from datetime import datetime, timezone

from .middleware import TraceIdFilter


_EXTRA_FIELDS = (
    "method",
    "path",
    "status",
    "duration_ms",
    "target",
    "scenarios",
)


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "trace_id": getattr(record, "trace_id", None),
            "msg": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(service_name: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service_name))
    handler.addFilter(TraceIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Uvicorn installs its own plain-text handlers; route its records through
    # the JSON handler instead so stdout stays one JSON object per line.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # Uvicorn's default access log duplicates our middleware log line.
    logging.getLogger("uvicorn.access").disabled = True
    # httpx logs every request at INFO; ServiceClient already logs outgoing calls.
    logging.getLogger("httpx").setLevel(logging.WARNING)
