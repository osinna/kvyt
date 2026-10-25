"""Landing page for the OAuth2 redirect of partner-app.

Shows what the authorization server put into the address: `code` and `state`
on success, `error` and `error_description` otherwise. Used when the code is
exchanged by hand, e.g. from Bruno or curl.
"""

import html

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)

_FIELDS = ("code", "state", "error", "error_description")

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KVYT · OAuth callback</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 640px; margin: 48px auto; padding: 0 16px; color: #1d1d27; }}
  dt {{ font-weight: 600; margin-top: 12px; }}
  dd {{ margin: 4px 0 0; }}
  code {{ display: block; padding: 8px 10px; background: #f4f4f7; border-radius: 6px;
          word-break: break-all; user-select: all; }}
  .error {{ color: #a01919; }}
</style>
</head>
<body>
<h1 class="{css}">{title}</h1>
<dl>{rows}</dl>
<p>{hint}</p>
</body>
</html>
"""


@router.get("/oauth/callback")
async def oauth_callback(request: Request) -> HTMLResponse:
    params = {name: request.query_params[name] for name in _FIELDS if name in request.query_params}
    rows = "".join(
        f"<dt>{name}</dt><dd><code>{html.escape(value)}</code></dd>" for name, value in params.items()
    )
    if "error" in params:
        title, css, hint = "Authorization failed", "error", "No code was issued."
    elif "code" in params:
        title, css = "Authorization code received", ""
        hint = (
            "Exchange the code within 5 minutes: POST /oauth/token with grant_type=authorization_code, "
            "this code, the same redirect_uri, client_id and your code_verifier. The code works once."
        )
    else:
        title, css, hint = "Nothing to show", "", "This page receives the redirect of an OAuth2 authorization."
    page = _PAGE.format(title=title, css=css, rows=rows or "", hint=html.escape(hint))
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})
