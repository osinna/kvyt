"""Public API description: the hand-written contract in openapi.yaml and Swagger UI over it.

The services' own generated schemas describe internal endpoints too and are not
exposed; this file is the contract clients rely on.
"""

from pathlib import Path

import yaml
from fastapi import APIRouter
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

SPEC_PATH = Path(__file__).resolve().parent.parent / "openapi.yaml"
SPEC_URL = "/openapi.json"

router = APIRouter(include_in_schema=False)
_spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


@router.get(SPEC_URL)
async def openapi_spec() -> JSONResponse:
    return JSONResponse(_spec)


@router.get("/docs")
async def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=SPEC_URL,
        title=f"{_spec['info']['title']} {_spec['info']['version']}",
        swagger_ui_parameters={"persistAuthorization": True},
    )
