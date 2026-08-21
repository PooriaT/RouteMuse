from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

ASGIScope = MutableMapping[str, Any]
ASGIReceive = Callable[[], Awaitable[MutableMapping[str, Any]]]
ASGISend = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[ASGIScope, ASGIReceive, ASGISend], Awaitable[None]]


class RedactOAuthCallbackQueryMiddleware:
    """Keep OAuth callback secrets out of Uvicorn's request-target access log."""

    def __init__(self, app: ASGIApp, callback_path: str) -> None:
        self.app = app
        self.callback_path = callback_path

    async def __call__(
        self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend
    ) -> None:
        if scope.get("type") != "http" or scope.get("path") != self.callback_path:
            await self.app(scope, receive, send)
            return

        downstream_scope = dict(scope)
        # Uvicorn retains the original scope for access logging. The downstream
        # copy still contains the callback parameters FastAPI must validate.
        scope["query_string"] = b""
        await self.app(downstream_scope, receive, send)
