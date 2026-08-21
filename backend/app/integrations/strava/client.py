from typing import Literal
from urllib.parse import urlencode, urlparse

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.strava.dtos import (
    StravaTokenExchangeDTO,
    StravaTokenRefreshDTO,
)
from app.integrations.strava.errors import (
    StravaAuthenticationInvalid,
    StravaConfigurationUnavailable,
    StravaTokenExchangeFailed,
    StravaTokenRefreshFailed,
    StravaTokenRevocationFailed,
)

STRAVA_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_REVOKE_URL = "https://www.strava.com/oauth/revoke"
REQUIRED_STRAVA_SCOPE = "activity:read_all"


class StravaOAuthClient:
    """Strava-specific OAuth HTTP behavior with secret-safe failures."""

    def __init__(
        self, settings: Settings, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    def authorization_url(self, state: str) -> str:
        client_id, _, redirect_uri = self._configuration()
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "approval_prompt": "auto",
                "scope": REQUIRED_STRAVA_SCOPE,
                "state": state,
            }
        )
        return f"{STRAVA_AUTHORIZE_URL}?{query}"

    async def exchange_code(self, code: str) -> StravaTokenExchangeDTO:
        client_id, client_secret, _ = self._configuration()
        try:
            response = await self._post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            return StravaTokenExchangeDTO.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise StravaTokenExchangeFailed(
                "Strava did not complete the token exchange."
            ) from exc

    async def refresh_token(self, refresh_token: str) -> StravaTokenRefreshDTO:
        client_id, client_secret, _ = self._configuration()
        try:
            response = await self._post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            if response.status_code == httpx.codes.UNAUTHORIZED:
                raise StravaAuthenticationInvalid(
                    "Stored Strava authentication is no longer valid."
                )
            response.raise_for_status()
            return StravaTokenRefreshDTO.model_validate(response.json())
        except StravaAuthenticationInvalid:
            raise
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise StravaTokenRefreshFailed(
                "Strava did not complete the token refresh."
            ) from exc

    async def revoke_token(
        self,
        token: str,
        *,
        token_type_hint: Literal["access_token", "refresh_token"],
    ) -> None:
        client_id, client_secret, _ = self._configuration()
        try:
            response = await self._post(
                STRAVA_REVOKE_URL,
                data={"token": token, "token_type_hint": token_type_hint},
                auth=httpx.BasicAuth(client_id, client_secret),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise StravaTokenRevocationFailed(
                "Strava did not confirm token revocation."
            ) from exc

    def _configuration(self) -> tuple[str, str, str]:
        client_id = self._settings.strava_client_id
        client_secret_setting = self._settings.strava_client_secret
        redirect_uri = self._settings.strava_redirect_uri
        client_secret = (
            client_secret_setting.get_secret_value()
            if client_secret_setting is not None
            else None
        )
        parsed_redirect = urlparse(redirect_uri) if redirect_uri else None
        if (
            not client_id
            or not client_secret
            or not redirect_uri
            or parsed_redirect is None
            or parsed_redirect.scheme not in {"http", "https"}
            or not parsed_redirect.netloc
        ):
            raise StravaConfigurationUnavailable(
                "Strava OAuth configuration is unavailable."
            )
        return client_id, client_secret, redirect_uri

    async def _post(self, url: str, **kwargs: object) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(url, **kwargs)
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.post(url, **kwargs)
