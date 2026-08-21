import asyncio
from typing import Any

from app.core.http import RedactOAuthCallbackQueryMiddleware


def test_callback_query_is_available_but_removed_from_access_log_scope() -> None:
    captured_scope: dict[str, Any] = {}

    async def downstream(scope: dict[str, Any], receive: Any, send: Any) -> None:
        captured_scope.update(scope)

    middleware = RedactOAuthCallbackQueryMiddleware(
        downstream, callback_path="/api/v1/strava/callback"
    )
    server_scope: dict[str, Any] = {
        "type": "http",
        "path": "/api/v1/strava/callback",
        "query_string": b"code=authorization-secret&state=nonce",
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        return None

    asyncio.run(middleware(server_scope, receive, send))

    assert server_scope["query_string"] == b""
    assert captured_scope["query_string"] == (
        b"code=authorization-secret&state=nonce"
    )
