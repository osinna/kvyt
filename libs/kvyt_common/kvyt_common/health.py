import logging
from typing import Awaitable, Callable

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .scenarios import ScenarioSet


DepCheck = Callable[[], Awaitable[bool]]


def build_health_router(
    service_name: str,
    service_version: str,
    scenarios: ScenarioSet,
    dep_checks: dict[str, DepCheck] | None = None,
) -> APIRouter:
    router = APIRouter()
    checks = dep_checks or {}

    @router.get("/health")
    async def health() -> dict:
        return {
            "service": service_name,
            "status": "ok",
            "version": service_version,
            "scenarios": scenarios.as_list(),
        }

    @router.get("/health/ready")
    async def ready() -> JSONResponse:
        deps: dict[str, str] = {}
        all_ok = True
        for name, check in checks.items():
            try:
                ok = await check()
            except Exception:
                logging.getLogger("kvyt.health").warning(
                    "dependency check failed",
                    extra={"target": name},
                    exc_info=True,
                )
                ok = False
            deps[name] = "ok" if ok else "fail"
            if not ok:
                all_ok = False
        payload = {
            "service": service_name,
            "status": "ok" if all_ok else "fail",
            "deps": deps,
        }
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content=payload,
        )

    return router


def make_postgres_check(engine: AsyncEngine) -> DepCheck:
    async def _check() -> bool:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    return _check


def make_http_check(url: str, timeout: float = 2.0) -> DepCheck:
    async def _check() -> bool:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
        return response.status_code == 200

    return _check
