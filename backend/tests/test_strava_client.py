import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import Settings
from app.integrations.strava.client import StravaOAuthClient
from app.integrations.strava.errors import (
    StravaAuthenticationInvalid,
    StravaRateLimited,
)


def _settings() -> Settings:
    return Settings(
        strava_client_id="12345",
        strava_client_secret="client-secret",
        strava_redirect_uri="http://localhost:8000/api/v1/strava/callback",
        _env_file=None,
    )


def test_refresh_posts_form_data_and_parses_rotated_refresh_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == httpx.URL("https://www.strava.com/oauth/token")
        assert parse_qs(request.content.decode()) == {
            "client_id": ["12345"],
            "client_secret": ["client-secret"],
            "grant_type": ["refresh_token"],
            "refresh_token": ["old-refresh"],
        }
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "rotated-refresh",
                "expires_at": 2_000_000_000,
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = StravaOAuthClient(_settings(), http_client=http_client)

    result = asyncio.run(client.refresh_token("old-refresh"))

    assert result.access_token.get_secret_value() == "new-access"
    assert result.refresh_token.get_secret_value() == "rotated-refresh"
    assert "new-access" not in repr(result)
    assert "rotated-refresh" not in repr(result)


def test_refresh_unauthorized_is_a_controlled_authentication_failure() -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(401))
    )
    client = StravaOAuthClient(_settings(), http_client=http_client)

    with pytest.raises(StravaAuthenticationInvalid) as error:
        asyncio.run(client.refresh_token("invalid-refresh-secret"))

    assert "invalid-refresh-secret" not in str(error.value)


def test_refresh_rate_limit_preserves_retry_metadata_without_token_leakage() -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(429, headers={"Retry-After": "75"})
        )
    )
    client = StravaOAuthClient(_settings(), http_client=http_client)

    with pytest.raises(StravaRateLimited) as error:
        asyncio.run(client.refresh_token("rate-limited-refresh-secret"))

    assert error.value.retry_after_seconds == 75
    assert "rate-limited-refresh-secret" not in str(error.value)
