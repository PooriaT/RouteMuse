"""Safe, provider-neutral failures exposed by LLM adapters."""


class LlmProviderError(Exception):
    """Base class for controlled LLM provider failures."""


class LlmConfigurationError(LlmProviderError):
    """Required provider configuration is absent."""


class LlmTimeoutError(LlmProviderError):
    """The provider did not respond within the configured bound."""


class LlmUnavailableError(LlmProviderError):
    """The provider could not be reached or rejected the request."""


class LlmModelUnavailableError(LlmProviderError):
    """The configured model is not installed at the provider."""


class LlmMalformedResponseError(LlmProviderError):
    """The provider returned a response RouteMuse cannot safely consume."""
