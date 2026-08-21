class StravaIntegrationError(RuntimeError):
    """Base class for safe, controlled Strava integration failures."""


class StravaConfigurationUnavailable(StravaIntegrationError):
    """Required Strava configuration is missing or invalid."""


class StravaPersistenceFailed(StravaIntegrationError):
    """The Strava connection could not be persisted safely."""


class StravaAuthorizationDenied(StravaIntegrationError):
    """The athlete declined the requested authorization."""


class StravaCallbackMalformed(StravaIntegrationError):
    """The OAuth callback did not contain a supported result."""


class StravaOAuthStateInvalid(StravaIntegrationError):
    """The OAuth state is absent, expired, or does not match."""


class StravaInsufficientScope(StravaIntegrationError):
    """The athlete did not grant the minimum required scope."""


class StravaTokenExchangeFailed(StravaIntegrationError):
    """The authorization code could not be exchanged safely."""


class StravaTokenRefreshFailed(StravaIntegrationError):
    """The access token could not be refreshed safely."""


class StravaTokenRevocationFailed(StravaIntegrationError):
    """The provider did not confirm token revocation."""


class StravaAuthenticationInvalid(StravaIntegrationError):
    """The stored Strava authentication is absent or no longer valid."""


class StravaRateLimited(StravaIntegrationError):
    """Strava refused the request because the current rate limit was reached."""

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class StravaRequestTimedOut(StravaIntegrationError):
    """The Strava activity request exceeded the configured timeout."""


class StravaTemporarilyUnavailable(StravaIntegrationError):
    """Strava returned a temporary server-side failure."""


class StravaMalformedResponse(StravaIntegrationError):
    """Strava returned activity data outside the integration contract."""


class StravaNetworkError(StravaIntegrationError):
    """An unexpected network failure prevented a Strava request."""


class StravaSynchronizationPersistenceFailed(StravaIntegrationError):
    """Synchronization progress could not be persisted safely."""
