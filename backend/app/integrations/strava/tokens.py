from datetime import UTC, datetime, timedelta

from app.db.repositories.strava import StravaConnectionRepository
from app.db.security import TokenProtectionError
from app.integrations.strava.client import StravaOAuthClient
from app.integrations.strava.errors import (
    StravaAuthenticationInvalid,
    StravaConfigurationUnavailable,
)

TOKEN_REFRESH_WINDOW = timedelta(hours=1)


class StravaTokenService:
    """Return a usable access token and persist every refresh-token rotation."""

    def __init__(
        self,
        repository: StravaConnectionRepository,
        oauth_client: StravaOAuthClient,
    ) -> None:
        self._repository = repository
        self._oauth_client = oauth_client

    async def usable_access_token(self) -> str:
        return await self._access_token(force_refresh=False)

    async def refresh_access_token(self) -> str:
        """Refresh through the centralized lifecycle after a provider 401."""

        return await self._access_token(force_refresh=True)

    async def _access_token(self, *, force_refresh: bool) -> str:
        try:
            connection = self._repository.get_current(for_update=True)
        except TokenProtectionError as exc:
            self._repository.rollback()
            raise StravaConfigurationUnavailable(
                "Protected Strava token material is unavailable."
            ) from exc
        if connection is None:
            self._repository.rollback()
            raise StravaAuthenticationInvalid("No Strava connection is available.")

        now = datetime.now(UTC)
        if (
            not force_refresh
            and connection.access_token_expires_at > now + TOKEN_REFRESH_WINDOW
        ):
            access_token = connection.access_token
            self._repository.commit()
            return access_token

        try:
            refreshed = await self._oauth_client.refresh_token(
                connection.refresh_token
            )
            connection.access_token = refreshed.access_token.get_secret_value()
            connection.refresh_token = refreshed.refresh_token.get_secret_value()
            connection.access_token_expires_at = datetime.fromtimestamp(
                refreshed.expires_at, tz=UTC
            )
            connection.updated_at = now
            access_token = connection.access_token
            self._repository.commit()
            return access_token
        except TokenProtectionError as exc:
            self._repository.rollback()
            raise StravaConfigurationUnavailable(
                "Protected Strava token storage is unavailable."
            ) from exc
        except Exception:
            self._repository.rollback()
            raise
