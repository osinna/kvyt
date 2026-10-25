"""OAuth2 provider for partner applications (RFC 6749, PKCE per RFC 7636).

Authorization Code with mandatory PKCE (S256) for applications acting for a
person, Client Credentials for services acting for themselves. Tokens are the
same JWTs as /auth/login issues, plus `scope` and `client_id` claims, and never
come with a refresh token.

Errors of /oauth/token use the RFC 6749 format, not the KVYT error envelope:
OAuth client libraries, Postman included, expect it.
"""

import base64
import hashlib
import html
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import OAuthClient, OAuthCode, User
from ..schemas import _normalize_email
from ..security import issue_access_token, verify_password

router = APIRouter(prefix="/oauth", tags=["oauth"])

GRANT_AUTHORIZATION_CODE = "authorization_code"
GRANT_CLIENT_CREDENTIALS = "client_credentials"
SERVICE_ROLE = "service"
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"

SCOPE_DESCRIPTIONS = {
    "profile:read": "See your profile: name, email and role",
    "bookings:read": "See your bookings",
    "bookings:write": "Create, confirm, cancel and delete bookings on your behalf",
    "occupancy:read": "See how many seats of a session are taken",
}

# RFC 7636: 43 to 128 characters of the unreserved set.
_PKCE_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _valid_pkce_value(value: str) -> bool:
    return 43 <= len(value) <= 128 and set(value) <= _PKCE_ALPHABET


def _form(body: bytes) -> dict[str, str]:
    """First value of every field of a urlencoded body."""
    return {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True).items()}


def _is_form(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    return content_type.split(";")[0].strip().lower() == FORM_CONTENT_TYPE


# --- Authorization endpoint --------------------------------------------------


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KVYT · {title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #f4f4f7; color: #1d1d27; margin: 0; }}
  main {{ max-width: 420px; margin: 48px auto; background: #fff; border-radius: 12px;
         padding: 28px 32px; box-shadow: 0 2px 12px rgba(0, 0, 0, .08); }}
  h1 {{ font-size: 20px; margin: 0 0 16px; }}
  .brand {{ font-weight: 700; letter-spacing: .08em; color: #5b3df5; margin-bottom: 12px; }}
  ul {{ padding-left: 20px; }}
  label {{ display: block; margin: 12px 0 4px; font-size: 14px; }}
  input[type=email], input[type=password] {{ width: 100%; box-sizing: border-box; padding: 8px 10px;
         border: 1px solid #c9c9d6; border-radius: 6px; font-size: 15px; }}
  .error {{ background: #fdecec; color: #a01919; padding: 10px 12px; border-radius: 6px; }}
  .buttons {{ display: flex; gap: 12px; margin-top: 20px; }}
  button {{ flex: 1; padding: 10px; border-radius: 6px; border: 1px solid #5b3df5; font-size: 15px;
         cursor: pointer; background: #fff; color: #5b3df5; }}
  button[value=allow] {{ background: #5b3df5; color: #fff; }}
</style>
</head>
<body><main><div class="brand">KVYT</div>{body}</main></body>
</html>
"""


def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(title=html.escape(title), body=body), status_code, headers=_NO_STORE)


def _error_page(message: str) -> HTMLResponse:
    """Shown instead of a redirect when the client or its redirect_uri cannot be trusted."""
    body = (
        "<h1>This authorization request is invalid</h1>"
        f'<p class="error">{html.escape(message)}</p>'
        "<p>Nothing was shared. Return to the application and try again.</p>"
    )
    return _page("Authorization error", body, 400)


@dataclass(frozen=True)
class AuthRequest:
    client: OAuthClient
    redirect_uri: str
    scopes: list[str]
    state: str | None
    code_challenge: str

    def hidden_fields(self) -> str:
        fields = {
            "response_type": "code",
            "client_id": self.client.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256",
        }
        if self.state is not None:
            fields["state"] = self.state
        return "".join(
            f'<input type="hidden" name="{name}" value="{html.escape(value)}">'
            for name, value in fields.items()
        )


def _redirect(redirect_uri: str, state: str | None, **params: str) -> RedirectResponse:
    if state is not None:
        params["state"] = state
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}{urlencode(params)}", 302, headers=_NO_STORE)


async def _parse_auth_request(
    db: AsyncSession, params: dict[str, str]
) -> AuthRequest | Response:
    """Validates an authorization request in the order RFC 6749, 4.1.2.1 requires:
    until client and redirect_uri are trusted, errors are shown, never redirected."""
    client_id = params.get("client_id", "")
    client = await db.get(OAuthClient, client_id) if client_id else None
    if client is None:
        return _error_page("Unknown client_id.")
    redirect_uri = params.get("redirect_uri", "")
    if redirect_uri not in client.redirect_uris:
        return _error_page("redirect_uri is not registered for this client.")

    state = params.get("state")
    if params.get("response_type") != "code":
        return _redirect(redirect_uri, state, error="unsupported_response_type",
                         error_description="response_type must be 'code'")
    if GRANT_AUTHORIZATION_CODE not in client.grant_types:
        return _redirect(redirect_uri, state, error="unauthorized_client",
                         error_description="This client may not use the authorization code flow")
    challenge = params.get("code_challenge", "")
    if not challenge or params.get("code_challenge_method") != "S256":
        return _redirect(redirect_uri, state, error="invalid_request",
                         error_description="PKCE is required: code_challenge with code_challenge_method=S256")
    if not _valid_pkce_value(challenge):
        return _redirect(redirect_uri, state, error="invalid_request",
                         error_description="code_challenge is malformed")
    scopes = params.get("scope", "").split() or list(client.scopes)
    if not set(scopes) <= set(client.scopes):
        return _redirect(redirect_uri, state, error="invalid_scope",
                         error_description="Requested scope is not allowed for this client")
    return AuthRequest(client, redirect_uri, list(dict.fromkeys(scopes)), state, challenge)


def _consent_page(auth: AuthRequest, email: str = "", error: str | None = None) -> HTMLResponse:
    items = "".join(f"<li>{html.escape(SCOPE_DESCRIPTIONS.get(s, s))}</li>" for s in auth.scopes)
    notice = f'<p class="error">{html.escape(error)}</p>' if error else ""
    body = (
        f"<h1>{html.escape(auth.client.name)} is requesting access</h1>"
        f"<p><b>{html.escape(auth.client.client_id)}</b> wants to:</p><ul>{items}</ul>"
        f"{notice}"
        '<form method="post" action="/oauth/authorize">'
        f"{auth.hidden_fields()}"
        '<label for="email">Email</label>'
        f'<input id="email" name="email" type="email" autocomplete="username" value="{html.escape(email)}">'
        '<label for="password">Password</label>'
        '<input id="password" name="password" type="password" autocomplete="current-password">'
        '<div class="buttons">'
        '<button type="submit" name="decision" value="deny" formnovalidate>Deny</button>'
        '<button type="submit" name="decision" value="allow">Allow</button>'
        "</div></form>"
    )
    # 401 lets gateway count a wrong password towards the failed login limit.
    return _page("Authorize", body, 401 if error else 200)


@router.get("/authorize")
async def authorize_page(request: Request, db: AsyncSession = Depends(get_session)) -> Response:
    auth = await _parse_auth_request(db, dict(request.query_params))
    if not isinstance(auth, AuthRequest):
        return auth
    return _consent_page(auth)


@router.post("/authorize")
async def authorize_decision(request: Request, db: AsyncSession = Depends(get_session)) -> Response:
    if not _is_form(request):
        return _error_page(f"The form must be sent as {FORM_CONTENT_TYPE}.")
    form = _form(await request.body())
    auth = await _parse_auth_request(db, form)
    if not isinstance(auth, AuthRequest):
        return auth
    if form.get("decision") != "allow":
        return _redirect(auth.redirect_uri, auth.state, error="access_denied",
                         error_description="The user denied access")

    raw_email = form.get("email", "")
    try:
        email = _normalize_email(raw_email)
    except ValueError:
        return _consent_page(auth, raw_email, "Email or password is incorrect.")
    user = await db.scalar(select(User).where(User.email == email))
    password_hash = user.password_hash if user else None
    if not await run_in_threadpool(verify_password, form.get("password", "")[:72], password_hash):
        return _consent_page(auth, raw_email, "Email or password is incorrect.")

    code = secrets.token_urlsafe(32)
    db.add(
        OAuthCode(
            code_hash=_hash_code(code),
            client_id=auth.client.client_id,
            user_id=user.id,
            redirect_uri=auth.redirect_uri,
            scope=" ".join(auth.scopes),
            code_challenge=auth.code_challenge,
            expires_at=_utcnow() + timedelta(seconds=get_settings().oauth_code_ttl_seconds),
        )
    )
    await db.commit()
    return _redirect(auth.redirect_uri, auth.state, code=code)


# --- Token endpoint ----------------------------------------------------------


class OAuthError(Exception):
    def __init__(self, error: str, description: str, status_code: int = 400) -> None:
        self.error = error
        self.description = description
        self.status_code = status_code


def _error_response(exc: OAuthError) -> JSONResponse:
    headers = dict(_NO_STORE)
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = 'Basic realm="kvyt"'
    return JSONResponse(
        {"error": exc.error, "error_description": exc.description},
        exc.status_code,
        headers=headers,
    )


def _basic_credentials(request: Request) -> tuple[str, str] | None:
    """client_secret_basic: id and secret are form-urlencoded before base64 (RFC 6749, 2.3.1)."""
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "basic" or not value:
        return None
    try:
        client_id, sep, secret = base64.b64decode(value.strip(), validate=True).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        raise OAuthError("invalid_client", "Authorization header is malformed", 401)
    if not sep:
        raise OAuthError("invalid_client", "Authorization header is malformed", 401)
    return unquote(client_id.replace("+", " ")), unquote(secret.replace("+", " "))


def _require(form: dict[str, str], *names: str) -> None:
    missing = [name for name in names if not form.get(name)]
    if missing:
        raise OAuthError("invalid_request", f"Missing parameter: {missing[0]}")


async def _authenticate_client(request: Request, form: dict[str, str], db: AsyncSession) -> OAuthClient:
    basic = _basic_credentials(request)
    if basic is not None:
        client_id, secret = basic
    else:
        client_id, secret = form.get("client_id", ""), form.get("client_secret")
    if not client_id:
        raise OAuthError("invalid_request", "Missing parameter: client_id")
    client = await db.get(OAuthClient, client_id)
    if client is None:
        raise OAuthError("invalid_client", "Unknown client", 401)
    if client.is_confidential and not (
        secret and await run_in_threadpool(verify_password, secret[:72], client.secret_hash)
    ):
        raise OAuthError("invalid_client", "Client authentication failed", 401)
    return client


def _token_response(token: str, scope: str) -> JSONResponse:
    return JSONResponse(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": get_settings().access_token_ttl_seconds,
            "scope": scope,
        },
        headers=_NO_STORE,
    )


async def _authorization_code_grant(client: OAuthClient, form: dict[str, str], db: AsyncSession) -> JSONResponse:
    _require(form, "code", "redirect_uri", "code_verifier")
    stored = await db.scalar(
        select(OAuthCode).where(OAuthCode.code_hash == _hash_code(form["code"])).with_for_update()
    )
    if stored is None or stored.used_at is not None or stored.expires_at <= _utcnow():
        raise OAuthError("invalid_grant", "Authorization code is invalid, expired or already used")
    # A presented code is spent whatever happens next: it is never redeemable twice.
    stored.used_at = _utcnow()
    await db.commit()
    if stored.client_id != client.client_id:
        raise OAuthError("invalid_grant", "Authorization code was issued to another client")
    if stored.redirect_uri != form["redirect_uri"]:
        raise OAuthError("invalid_grant", "redirect_uri does not match the authorization request")
    verifier = form["code_verifier"]
    if not _valid_pkce_value(verifier) or not secrets.compare_digest(_s256(verifier), stored.code_challenge):
        raise OAuthError("invalid_grant", "code_verifier does not match code_challenge")
    user = await db.get(User, stored.user_id)
    if user is None:
        raise OAuthError("invalid_grant", "User no longer exists")
    token = issue_access_token(user.id, user.role, scope=stored.scope, client_id=client.client_id)
    return _token_response(token, stored.scope)


def _client_credentials_grant(client: OAuthClient, form: dict[str, str]) -> JSONResponse:
    scopes = form.get("scope", "").split() or list(client.scopes)
    if not set(scopes) <= set(client.scopes):
        raise OAuthError("invalid_scope", "Requested scope is not allowed for this client")
    scope = " ".join(dict.fromkeys(scopes))
    token = issue_access_token(f"client:{client.client_id}", SERVICE_ROLE, scope=scope, client_id=client.client_id)
    return _token_response(token, scope)


@router.post("/token")
async def token(request: Request, db: AsyncSession = Depends(get_session)) -> Response:
    try:
        if not _is_form(request):
            raise OAuthError("invalid_request", f"Content-Type must be {FORM_CONTENT_TYPE}")
        form = _form(await request.body())
        _require(form, "grant_type")
        grant_type = form["grant_type"]
        if grant_type not in (GRANT_AUTHORIZATION_CODE, GRANT_CLIENT_CREDENTIALS):
            raise OAuthError("unsupported_grant_type", f"Grant type '{grant_type}' is not supported")
        client = await _authenticate_client(request, form, db)
        if grant_type not in client.grant_types:
            raise OAuthError("unauthorized_client", f"This client may not use the {grant_type} grant")
        if grant_type == GRANT_AUTHORIZATION_CODE:
            return await _authorization_code_grant(client, form, db)
        return _client_credentials_grant(client, form)
    except OAuthError as exc:
        return _error_response(exc)
