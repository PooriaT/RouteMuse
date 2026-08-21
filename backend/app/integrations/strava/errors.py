class StravaIntegrationError(RuntimeError):
    """Base class for safe, controlled Strava integration failures."""


class StravaConfigurationUnavailable(StravaIntegrationError):
    """Required Strava configuration is missing or invalid."""


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
