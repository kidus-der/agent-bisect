"""A pure-ASGI (not `BaseHTTPMiddleware`) security-headers middleware.

`@app.middleware("http")`/`BaseHTTPMiddleware` buffers a `StreamingResponse`
in this Starlette version (verified: `/api/live/stream` never delivered its
first SSE frame through it -- confirmed by a bounded-timeout test before
this fix existed). A plain ASGI middleware that only touches the
`http.response.start` message doesn't buffer anything, so it's the correct
tool here regardless of the bug -- it works by construction, not by luck.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"

_EXTRA_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"content-security-policy", CSP.encode()),
    (b"referrer-policy", b"no-referrer"),
)


class SecurityHeadersMiddleware:
    """Adds fixed security headers to `http.response.start`, streaming-safe."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(_EXTRA_HEADERS)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
