from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import PlainTextResponse


Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class RequestBodyLimitMiddleware:
    """Bound and replay a request body before framework parsing begins."""

    def __init__(
        self,
        app: Any,
        *,
        max_bytes: int,
        allowed_origins: tuple[str, ...] = (),
        is_production: bool = False,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.allowed_origins = allowed_origins
        self.is_production = is_production

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length", b"").decode("ascii", errors="ignore")
        if content_length.isdigit() and int(content_length) > self.max_bytes:
            await self._reject(scope, receive, send, headers)
            return

        received = 0
        buffered: deque[dict[str, Any]] = deque()
        more_body = True
        while more_body:
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    await self._reject(scope, receive, send, headers)
                    return
                more_body = bool(message.get("more_body", False))
            else:
                more_body = False
            buffered.append(message)

        async def replay_receive() -> dict[str, Any]:
            if buffered:
                return buffered.popleft()
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _reject(
        self,
        scope: dict[str, Any],
        receive: Receive,
        send: Send,
        request_headers: dict[bytes, bytes],
    ) -> None:
        response_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "Cache-Control": "no-store" if str(scope.get("path", "")).startswith("/api/v1") else "no-cache",
        }
        if self.is_production:
            response_headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        origin = request_headers.get(b"origin", b"").decode("utf-8", errors="ignore")
        if origin and origin in self.allowed_origins:
            response_headers["Access-Control-Allow-Origin"] = origin
            response_headers["Vary"] = "Origin"
        response = PlainTextResponse("Request body is too large", status_code=413, headers=response_headers)
        await response(scope, receive, send)
