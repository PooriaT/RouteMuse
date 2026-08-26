"""Deterministic, provider-neutral orchestration of factual route candidates."""

from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from app.domain.planning import RoutePlanningRequest
from app.domain.routes import (
    CandidateGenerationProvenance,
    CandidateGenerationResult,
    GeoJsonLineString,
    RoundTripParameters,
    RouteCandidate,
    RouteShape,
    RoutingRequest,
)
from app.integrations.contracts import RoutingProvider
from app.integrations.routing.errors import (
    NoRouteFoundError,
    RouteProviderTemporaryError,
)
from app.services.geometry_cells import geometry_cells, shared_projection_origin

GENERATION_ALGORITHM_VERSION = "routemuse-round-trip-v1"
DESIRED_CANDIDATES = 4
MAX_ATTEMPTS = 8
ROUND_TRIP_POINTS = 4
TARGET_DISTANCE_FACTORS = (1.0, 0.9, 1.1, 0.95, 1.05)
# The hosted ORS Directions service rejects round trips above this request length.
MAX_EFFECTIVE_TARGET_DISTANCE_METERS = 100_000.0
ROUTE_SIMILARITY_THRESHOLD = 0.8


class CandidateGenerationError(Exception):
    """A controlled application failure with an API-safe stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def deterministic_seeds(request: RoutePlanningRequest, count: int) -> list[int]:
    """Derive unsigned 32-bit seeds from canonical inputs with SHA-256."""
    distance = request.target_distance_meters
    if distance is None:
        raise CandidateGenerationError(
            "route_target_distance_required",
            "A resolved target distance is required to generate route candidates.",
        )
    area = request.planning_area
    canonical = "|".join(
        (
            GENERATION_ALGORITHM_VERSION,
            f"{area.longitude:.7f}",
            f"{area.latitude:.7f}",
            request.activity_kind.value,
            f"{distance:.3f}",
        )
    )
    base = sha256(canonical.encode()).digest()
    return [
        int.from_bytes(sha256(base + index.to_bytes(4, "big")).digest()[:4], "big")
        for index in range(count)
    ]


def effective_target_distances(
    target_distance_meters: float, count: int
) -> list[float]:
    """Return the documented repeating, deterministic target pattern."""
    return [
        target_distance_meters
        * TARGET_DISTANCE_FACTORS[index % len(TARGET_DISTANCE_FACTORS)]
        for index in range(count)
    ]


def _candidate_name(
    request: RoutePlanningRequest, candidate: RouteCandidate
) -> str:
    area = request.planning_area.display_name.partition(",")[0].strip()
    activity = request.activity_kind.value.replace("_", " ").title()
    shape = (
        candidate.route_shape.value.replace("_", " ").title()
        if candidate.route_shape is not None
        else "Route"
    )
    return f"{area} · {candidate.distance_meters / 1_000:.1f} km {activity} {shape}"


async def generate_route_candidates(
    request: RoutePlanningRequest, provider: RoutingProvider
) -> CandidateGenerationResult:
    """Make sequential bounded routing attempts and retain unique candidates."""
    if request.target_distance_meters is None:
        raise CandidateGenerationError(
            "route_target_distance_required",
            "A resolved target distance is required to generate route candidates.",
        )
    if request.route_shape not in {None, RouteShape.LOOP}:
        raise CandidateGenerationError(
            "unsupported_generation_mode",
            "Only loop candidate generation is currently supported.",
        )

    seeds = deterministic_seeds(request, MAX_ATTEMPTS)
    targets = effective_target_distances(request.target_distance_meters, MAX_ATTEMPTS)
    candidates: list[RouteCandidate] = []
    attempts_made = 0
    limit_skips = 0
    temporary_failures = 0
    for attempt_index, (seed, target) in enumerate(zip(seeds, targets, strict=True)):
        if len(candidates) == DESIRED_CANDIDATES:
            break
        if target > MAX_EFFECTIVE_TARGET_DISTANCE_METERS:
            limit_skips += 1
            continue
        attempts_made += 1
        routing_request = RoutingRequest(
            activity_kind=request.activity_kind,
            start=(request.planning_area.longitude, request.planning_area.latitude),
            round_trip=RoundTripParameters(
                target_distance_meters=target,
                points=ROUND_TRIP_POINTS,
                seed=seed,
            ),
        )
        try:
            candidate = await provider.route(routing_request)
        except NoRouteFoundError:
            continue
        except RouteProviderTemporaryError:
            temporary_failures += 1
            continue

        generation = CandidateGenerationProvenance(
            algorithm_version=GENERATION_ALGORITHM_VERSION,
            requested_distance_meters=request.target_distance_meters,
            effective_target_distance_meters=target,
            seed=seed,
            round_trip_points=ROUND_TRIP_POINTS,
            attempt_index=attempt_index,
        )
        candidate = RouteCandidate.model_validate(
            candidate.model_dump()
            | {
                "id": uuid5(
                    NAMESPACE_URL,
                    f"{GENERATION_ALGORITHM_VERSION}:{seed}:{attempt_index}",
                ),
                "name": _candidate_name(request, candidate),
                "generation_provenance": generation,
                "difficulty_score": None,
                "athlete_fit_score": None,
                "excitement_score": None,
                "novelty_score": None,
                "confidence_score": None,
                "explanation": None,
            }
        )
        if not any(
            geometries_are_similar(candidate.geometry, existing.geometry)
            for existing in candidates
        ):
            candidates.append(candidate)

    if not candidates:
        if attempts_made and temporary_failures == attempts_made:
            raise RouteProviderTemporaryError
        code = (
            "route_target_exceeds_provider_limit"
            if limit_skips == MAX_ATTEMPTS
            else "no_route_candidates"
        )
        message = (
            "The target distance exceeds the supported round-trip limit."
            if code == "route_target_exceeds_provider_limit"
            else "No route candidates could be generated within the attempt limit."
        )
        raise CandidateGenerationError(code, message)

    warnings: list[str] = []
    if limit_skips:
        warnings.append("target_variants_exceeded_provider_limit")
    if len(candidates) < DESIRED_CANDIDATES:
        warnings.append("fewer_candidates_than_desired")
    return CandidateGenerationResult(
        candidates=candidates,
        desired_candidates=DESIRED_CANDIDATES,
        attempts_made=attempts_made,
        max_attempts=MAX_ATTEMPTS,
        warnings=warnings,
    )


def geometries_are_similar(
    first: GeoJsonLineString,
    second: GeoJsonLineString,
    *,
    threshold: float = ROUTE_SIMILARITY_THRESHOLD,
) -> bool:
    """Compare direction-independent, tolerance-buffered sampled spatial cells."""
    reference_latitude, reference_longitude = shared_projection_origin([first, second])
    cells_a = geometry_cells(first, reference_latitude, reference_longitude)
    cells_b = geometry_cells(second, reference_latitude, reference_longitude)
    union = cells_a | cells_b
    return bool(union) and len(cells_a & cells_b) / len(union) >= threshold
