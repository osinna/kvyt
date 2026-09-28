import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from kvyt_common import (
    DefaultCacheControlMiddleware,
    TraceIdMiddleware,
    build_health_router,
    configure_logging,
    make_postgres_check,
    register_exception_handlers,
)

from . import catalog_client
from . import models  # noqa: F401  registers tables on Base.metadata
from .api import bookings, internal
from .config import get_settings
from .db import Base, database
from .scenarios import SERVICE_NAME, scenarios

API_PREFIX = "/api/v1"

settings = get_settings()
configure_logging(SERVICE_NAME, settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.getLogger("kvyt.startup").info(
        "service starting",
        extra={"scenarios": scenarios.as_list()},
    )
    await database.create_schema(Base.metadata)
    catalog_client.open_client()
    yield
    await catalog_client.close_client()
    await database.dispose()


app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)
app.add_middleware(DefaultCacheControlMiddleware)
app.add_middleware(TraceIdMiddleware)
register_exception_handlers(app)
app.include_router(
    build_health_router(
        SERVICE_NAME,
        settings.service_version,
        scenarios,
        # Not catalog: catalog and booking call each other, and a mutual
        # readiness check would deadlock compose startup. See make doctor.
        dep_checks={"postgres": make_postgres_check(database.engine)},
    )
)
app.include_router(bookings.router, prefix=API_PREFIX)
app.include_router(internal.router)
