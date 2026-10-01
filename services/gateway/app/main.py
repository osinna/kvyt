import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from kvyt_common import (
    DefaultCacheControlMiddleware,
    TraceIdMiddleware,
    build_health_router,
    configure_logging,
    make_http_check,
    register_exception_handlers,
)

from . import docs, proxy
from .config import get_settings
from .scenarios import SERVICE_NAME, scenarios

settings = get_settings()
configure_logging(SERVICE_NAME, settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.getLogger("kvyt.startup").info(
        "service starting",
        extra={"scenarios": scenarios.as_list()},
    )
    proxy.clients.update(proxy.build_clients())
    yield
    for client in proxy.clients.values():
        await client.aclose()


# The generated schema would describe the proxy, not the API; docs.py serves the real one.
app = FastAPI(title=SERVICE_NAME, lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None)
app.add_middleware(DefaultCacheControlMiddleware)
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
app.include_router(docs.router)
app.include_router(proxy.router)
