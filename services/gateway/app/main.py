import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from kvyt_common import (
    TraceIdMiddleware,
    build_health_router,
    configure_logging,
    make_http_check,
    parse_scenarios,
    register_exception_handlers,
)

from .config import get_settings

SERVICE_NAME = "gateway"

settings = get_settings()
configure_logging(SERVICE_NAME, settings.log_level)
scenarios = parse_scenarios(settings.bug_scenario, SERVICE_NAME)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.getLogger("kvyt.startup").info(
        "service starting",
        extra={"scenarios": scenarios.as_list()},
    )
    yield


app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)
app.add_middleware(TraceIdMiddleware)
register_exception_handlers(app)
app.include_router(
    build_health_router(
        SERVICE_NAME,
        settings.service_version,
        scenarios,
        dep_checks={
            "identity": make_http_check(f"{settings.identity_url}/health"),
            "catalog": make_http_check(f"{settings.catalog_url}/health"),
            "booking": make_http_check(f"{settings.booking_url}/health"),
        },
    )
)
