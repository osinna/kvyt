import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from kvyt_common import (
    DefaultCacheControlMiddleware,
    HttpMethodsMiddleware,
    TraceIdMiddleware,
    build_health_router,
    configure_logging,
    make_postgres_check,
    register_exception_handlers,
)

from . import models
from .api import notifications
from .bootstrap import ensure_database
from .config import get_settings
from .consumer import consumer
from .db import Base, database
from .scenarios import SERVICE_NAME, scenarios

API_PREFIX = "/api/v1"

settings = get_settings()
configure_logging(SERVICE_NAME, settings.log_level)


async def _broker_check() -> bool:
    return consumer.is_connected()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.getLogger("kvyt.startup").info(
        "service starting",
        extra={"scenarios": scenarios.as_list()},
    )
    await ensure_database()
    await database.create_schema(Base.metadata)
    await database.sync_index(
        models.ONE_PER_EVENT_INDEX,
        models.ONE_PER_EVENT_SQL,
        wanted=not scenarios.active("quartz"),
    )
    await consumer.start()
    yield
    await consumer.stop()
    await database.dispose()


app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)
app.add_middleware(HttpMethodsMiddleware, router=app.router)
app.add_middleware(DefaultCacheControlMiddleware)
app.add_middleware(TraceIdMiddleware)
register_exception_handlers(app)
app.include_router(
    build_health_router(
        SERVICE_NAME,
        settings.service_version,
        scenarios,
        dep_checks={
            "postgres": make_postgres_check(database.engine),
            "broker": _broker_check,
        },
    )
)
app.include_router(notifications.router, prefix=API_PREFIX)
