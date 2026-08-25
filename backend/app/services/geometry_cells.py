"""Provider-neutral local metric projection, sampling, and spatial cells."""

from math import atan2, cos, degrees, hypot, radians, sin

from app.domain.routes import GeoJsonLineString

GEOMETRY_SAMPLE_INTERVAL_METERS = 50.0
GEOMETRY_CELL_SIZE_METERS = 40.0


def shared_projection_origin(
    geometries: list[GeoJsonLineString],
) -> tuple[float, float]:
    coordinates = [point for geometry in geometries for point in geometry.coordinates]
    latitude = sum(point[1] for point in coordinates) / len(coordinates)
    longitudes = [radians(point[0]) for point in coordinates]
    longitude = degrees(
        atan2(
            sum(sin(value) for value in longitudes),
            sum(cos(value) for value in longitudes),
        )
    )
    return latitude, longitude


def geometry_cells(
    geometry: GeoJsonLineString,
    reference_latitude: float,
    reference_longitude: float,
) -> set[tuple[int, int]]:
    longitude_scale = 111_320.0 * cos(radians(reference_latitude))
    longitude_deltas = continuous_longitude_deltas(
        [point[0] for point in geometry.coordinates], reference_longitude
    )
    projected = [
        (
            longitude_delta * longitude_scale,
            (point[1] - reference_latitude) * 110_540.0,
        )
        for point, longitude_delta in zip(
            geometry.coordinates, longitude_deltas, strict=True
        )
    ]
    cells: set[tuple[int, int]] = set()
    for x, y in resample(projected):
        cell_x = round(x / GEOMETRY_CELL_SIZE_METERS)
        cell_y = round(y / GEOMETRY_CELL_SIZE_METERS)
        cells.update(
            (cell_x + dx, cell_y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        )
    return cells


def wrapped_longitude_delta(longitude: float, reference: float) -> float:
    return (longitude - reference + 180.0) % 360.0 - 180.0


def continuous_longitude_deltas(
    longitudes: list[float], reference: float
) -> list[float]:
    """Unwrap one line continuously on a branch chosen independently of direction."""
    longitude_radians = [radians(longitude) for longitude in longitudes]
    route_origin = degrees(
        atan2(
            sum(sin(value) for value in longitude_radians),
            sum(cos(value) for value in longitude_radians),
        )
    )
    route_origin_delta = wrapped_longitude_delta(route_origin, reference)
    unwrapped = [
        route_origin_delta + wrapped_longitude_delta(longitudes[0], route_origin)
    ]
    for previous, current in zip(longitudes, longitudes[1:], strict=False):
        unwrapped.append(
            unwrapped[-1] + wrapped_longitude_delta(current, previous)
        )
    return unwrapped


def resample(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    sampled = [points[0]]
    carry = 0.0
    for start, end in zip(points, points[1:], strict=False):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = hypot(dx, dy)
        if not length:
            continue
        distance = GEOMETRY_SAMPLE_INTERVAL_METERS - carry
        while distance <= length:
            ratio = distance / length
            sampled.append((start[0] + dx * ratio, start[1] + dy * ratio))
            distance += GEOMETRY_SAMPLE_INTERVAL_METERS
        carry = (carry + length) % GEOMETRY_SAMPLE_INTERVAL_METERS
    sampled.append(points[-1])
    return sampled
