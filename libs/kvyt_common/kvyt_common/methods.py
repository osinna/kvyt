"""HEAD, OPTIONS and the Allow header, derived from the routes a service declares.

FastAPI answers HEAD and OPTIONS with 405 and sends 405 without Allow. This
middleware fills the gap for every path the service knows:

- HEAD is served as GET without the body, so headers match what GET returns;
- OPTIONS answers 204 with Allow listing the methods of that path;
- any 405 carries Allow.

Paths the service does not know are passed through untouched and end as 404.
"""

from starlette.routing import Match, Router
from starlette.types import ASGIApp, Message, Receive, Scope, Send


_ORDER = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")


def allowed_methods(router: Router, scope: Scope) -> list[str]:
    methods: set[str] = set()
    for route in router.routes:
        route_methods = getattr(route, "methods", None)
        if not route_methods:
            continue
        match, _ = route.matches(scope)
        if match != Match.NONE:
            methods |= route_methods
    if not methods:
        return []
    if "GET" in methods:
        methods.add("HEAD")
    methods.add("OPTIONS")
    return [m for m in _ORDER if m in methods]


class HttpMethodsMiddleware:
    def __init__(self, app: ASGIApp, router: Router) -> None:
        self.app = app
        self.router = router

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        allowed = allowed_methods(self.router, scope)
        allow_header = (b"allow", ", ".join(allowed).encode())
        method = scope["method"]

        if method == "OPTIONS" and allowed:
            # Trace id and Cache-Control are added by the outer middleware.
            headers = [allow_header, (b"content-length", b"0")]
            await send({"type": "http.response.start", "status": 204, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return

        head = method == "HEAD" and "GET" in allowed
        if head:
            scope = {**scope, "method": "GET"}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] == 405 and allowed:
                message = {**message, "headers": [*message.get("headers", []), allow_header]}
            elif message["type"] == "http.response.body" and head:
                message = {**message, "body": b""}
            await send(message)

        await self.app(scope, receive, send_wrapper)
