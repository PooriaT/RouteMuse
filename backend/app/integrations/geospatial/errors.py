class GeocodingError(Exception):
    """Safe base error for failures at the geocoding boundary."""


class GeocoderNotConfiguredError(GeocodingError):
    pass


class GeocoderTimeoutError(GeocodingError):
    pass


class GeocoderRateLimitError(GeocodingError):
    pass


class GeocoderTemporaryError(GeocodingError):
    pass


class GeocoderMalformedResponseError(GeocodingError):
    pass
