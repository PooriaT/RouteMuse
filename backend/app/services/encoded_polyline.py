"""Translate Strava encoded summary geometry into canonical RouteMuse geometry."""

from app.domain.routes import GeoJsonLineString


def decode_summary_polyline(encoded: str) -> GeoJsonLineString:
    """Decode Google's encoded-polyline format into GeoJSON longitude/latitude."""
    coordinates: list[tuple[float, float]] = []
    latitude = longitude = index = 0
    while index < len(encoded):
        latitude_delta, index = _decode_value(encoded, index)
        longitude_delta, index = _decode_value(encoded, index)
        latitude += latitude_delta
        longitude += longitude_delta
        coordinates.append((longitude / 100_000, latitude / 100_000))
    if len(coordinates) < 2:
        raise ValueError("summary polyline must contain at least two coordinates")
    try:
        return GeoJsonLineString(coordinates=coordinates)
    except ValueError as exc:
        raise ValueError("summary polyline contains invalid coordinates") from exc


def _decode_value(encoded: str, index: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if index >= len(encoded):
            raise ValueError("truncated summary polyline")
        value = ord(encoded[index]) - 63
        index += 1
        if not 0 <= value <= 63 or shift > 30:
            raise ValueError("malformed summary polyline")
        result |= (value & 0x1F) << shift
        shift += 5
        if value < 0x20:
            break
    delta = ~(result >> 1) if result & 1 else result >> 1
    return delta, index
