import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from kvyt_common import (
    DefaultCacheControlMiddleware,
    ServiceClient,
    TraceIdMiddleware,
    build_health_router,
    configure_logging,
    forwardable_headers,
    make_http_check,
    register_exception_handlers,
    relay_response,
)
from kvyt_common.cache import REVALIDATE

from .assets import load_assets
from .config import get_settings
from .scenarios import SERVICE_NAME, scenarios

settings = get_settings()
configure_logging(SERVICE_NAME, settings.log_level)

assets = load_assets(scenarios, SERVICE_NAME)
gateway: ServiceClient | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global gateway
    logging.getLogger("kvyt.startup").info(
        "service starting",
        extra={"scenarios": scenarios.as_list()},
    )
    gateway = ServiceClient("gateway", settings.gateway_url, settings.upstream_timeout_seconds)
    yield
    await gateway.aclose()


app = FastAPI(title=SERVICE_NAME, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(DefaultCacheControlMiddleware)
app.add_middleware(TraceIdMiddleware)
register_exception_handlers(app)
app.include_router(
    build_health_router(
        SERVICE_NAME,
        settings.service_version,
        scenarios,
        dep_checks={"gateway": make_http_check(f"{settings.gateway_url}/health")},
    )
)


def _serve(url: str):
    asset = assets[url]

    async def handler(request: Request) -> Response:
        headers = {"Cache-Control": REVALIDATE, "ETag": asset.etag}
        if request.headers.get("if-none-match") == asset.etag:
            return Response(status_code=304, headers=headers)
        return Response(asset.content, media_type=asset.media_type, headers=headers)

    return handler


for _url in assets:
    app.add_api_route(_url, _serve(_url), methods=["GET"], include_in_schema=False)


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def api_proxy(request: Request) -> Response:
    """The browser talks to one origin; API calls are passed to gateway as is."""
    assert gateway is not None
    upstream = await gateway.request(
        request.method,
        request.url.path,
        params=request.query_params.multi_items(),
        headers=forwardable_headers(request.headers),
        content=await request.body(),
    )
    return relay_response(upstream)
