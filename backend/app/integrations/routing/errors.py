"""Safe errors shared by route discovery and routing adapters."""


class RouteProviderError(Exception):
    """Base provider failure whose fixed messages are safe for an API response."""


class ProviderConfigurationError(RouteProviderError):
    def __init__(self) -> None:
        super().__init__("Route provider is not configured")


class UnsupportedActivityError(RouteProviderError):
    def __init__(self) -> None:
        super().__init__("The provider does not support this activity")


class ProviderAuthenticationError(RouteProviderError):
    def __init__(self) -> None:
        super().__init__("The route provider rejected its credentials")


class ProviderInvalidRequestError(RouteProviderError):
    def __init__(self) -> None:
        super().__init__("The route provider rejected the routing request")


class RouteProviderTimeoutError(RouteProviderError):
    def __init__(self) -> None:
        super().__init__("The route provider timed out")


class RouteProviderRateLimitError(RouteProviderError):
    def __init__(self, retry_after_seconds: int | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("The route provider rate limit was reached")


class RouteProviderTemporaryError(RouteProviderError):
    def __init__(self) -> None:
        super().__init__("The route provider is temporarily unavailable")


class RouteProviderMalformedResponseError(RouteProviderError):
    def __init__(self) -> None:
        super().__init__("The route provider returned an invalid response")


class NoRouteFoundError(RouteProviderError):
    def __init__(self) -> None:
        super().__init__("No route was found")
