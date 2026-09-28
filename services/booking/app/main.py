import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from kvyt_common import (
    TraceIdMiddleware,
    build_health_router,
    configure_logging,
    make_postgres_check,
    parse_scenarios,
    register_exception_handlers,
)

from .config import get_settings

SERVICE_NAME = "booking"

settings = get_settings()
configure_logging(SERVICE_NAME, settings.log_level)
scenarios = parse_scenarios(settings.bug_scenario, SERVICE_NAME)

engine = create_async_engine(settings.database_url, pool_pre_ping=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.getLogger("kvyt.startup").info(
        "service starting",
        extra={"scenarios": scenarios.as_list()},
    )
    yield
    await engine.dispose()


app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)
app.add_middleware(TraceIdMiddleware)
register_exception_handlers(app)
app.include_router(
    build_health_router(
        SERVICE_NAME,
        settings.service_version,
        scenarios,
        dep_checks={"postgres": make_postgres_check(engine)},
    )
)
