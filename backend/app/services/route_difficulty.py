"""Pure, deterministic scoring of a route's intrinsic factual difficulty."""

from dataclasses import dataclass

from app.domain.activities import ActivityKind
from app.domain.recommendations import RouteDifficultyAssessment, ScoreComponent
from app.domain.routes import DistanceBreakdown, RouteCandidate

DIFFICULTY_SCORING_VERSION = "difficulty-v1"


class UnsupportedDifficultyScoringError(ValueError):
    """The activity has no reviewed RouteMuse difficulty calibration."""


@dataclass(frozen=True)
class ActivityDifficultyCalibration:
    """Centralized product heuristics; these are not an official grading standard."""

    distance_anchors: tuple[tuple[float, float], ...]
    elevation_anchors: tuple[tuple[float, float], ...]
    climbing_density_anchors: tuple[tuple[float, float], ...]
    component_weights: dict[str, float]
    surface_severity: dict[str, float]


_WALKING_SURFACE = {
    "paved": 0.05,
    "asphalt": 0.05,
    "concrete": 0.05,
    "paving_stones": 0.1,
    "compacted_gravel": 0.15,
    "fine_gravel": 0.2,
    "gravel": 0.3,
    "unpaved": 0.35,
    "dirt": 0.35,
    "ground": 0.4,
    "grass": 0.45,
    "sand": 0.75,
    "ice": 1.0,
    "cobblestone": 0.35,
    "wood": 0.25,
    "woodchips": 0.35,
    "grass_paving": 0.2,
    "metal": 0.15,
}
_HIKING_SURFACE = _WALKING_SURFACE | {
    "unpaved": 0.2,
    "dirt": 0.2,
    "ground": 0.25,
    "grass": 0.3,
}
_ROAD_SURFACE = _WALKING_SURFACE | {
    "paving_stones": 0.35,
    "compacted_gravel": 0.55,
    "fine_gravel": 0.65,
    "gravel": 0.8,
    "unpaved": 0.9,
    "dirt": 0.95,
    "ground": 0.95,
    "grass": 1.0,
    "sand": 1.0,
    "cobblestone": 0.65,
}
_GRAVEL_SURFACE = _ROAD_SURFACE | {
    "compacted_gravel": 0.1,
    "fine_gravel": 0.15,
    "gravel": 0.2,
    "unpaved": 0.3,
    "dirt": 0.35,
    "ground": 0.4,
    "grass": 0.55,
}
_MTB_SURFACE = _GRAVEL_SURFACE | {
    "gravel": 0.1,
    "unpaved": 0.15,
    "dirt": 0.15,
    "ground": 0.2,
    "grass": 0.35,
    "sand": 0.7,
}

# Anchors are (canonical factual unit, normalized score) and interpolate linearly.
CALIBRATIONS: dict[ActivityKind, ActivityDifficultyCalibration] = {
    ActivityKind.WALKING: ActivityDifficultyCalibration(
        ((0, 0), (5_000, 0.3), (15_000, 0.7), (30_000, 1)),
        ((0, 0), (200, 0.3), (800, 0.75), (1_500, 1)),
        ((0, 0), (20, 0.3), (60, 0.75), (120, 1)),
        {
            "distance": 0.35,
            "elevation_gain": 0.25,
            "climbing_density": 0.2,
            "surface": 0.1,
            "steepness": 0.1,
        },
        _WALKING_SURFACE,
    ),
    ActivityKind.HIKING: ActivityDifficultyCalibration(
        ((0, 0), (8_000, 0.3), (20_000, 0.7), (40_000, 1)),
        ((0, 0), (400, 0.3), (1_200, 0.7), (2_500, 1)),
        ((0, 0), (30, 0.25), (80, 0.7), (150, 1)),
        {
            "distance": 0.25,
            "elevation_gain": 0.2,
            "climbing_density": 0.15,
            "surface": 0.1,
            "steepness": 0.1,
            "trail_difficulty": 0.2,
        },
        _HIKING_SURFACE,
    ),
    ActivityKind.ROAD_CYCLING: ActivityDifficultyCalibration(
        ((0, 0), (30_000, 0.25), (80_000, 0.65), (160_000, 1)),
        ((0, 0), (500, 0.25), (1_500, 0.65), (3_500, 1)),
        ((0, 0), (10, 0.2), (30, 0.65), (70, 1)),
        {
            "distance": 0.35,
            "elevation_gain": 0.25,
            "climbing_density": 0.15,
            "surface": 0.15,
            "steepness": 0.1,
        },
        _ROAD_SURFACE,
    ),
    ActivityKind.GRAVEL_CYCLING: ActivityDifficultyCalibration(
        ((0, 0), (25_000, 0.25), (70_000, 0.65), (140_000, 1)),
        ((0, 0), (500, 0.25), (1_500, 0.65), (3_500, 1)),
        ((0, 0), (10, 0.2), (35, 0.65), (80, 1)),
        {
            "distance": 0.3,
            "elevation_gain": 0.25,
            "climbing_density": 0.15,
            "surface": 0.2,
            "steepness": 0.1,
        },
        _GRAVEL_SURFACE,
    ),
    ActivityKind.MOUNTAIN_BIKING: ActivityDifficultyCalibration(
        ((0, 0), (15_000, 0.3), (40_000, 0.7), (80_000, 1)),
        ((0, 0), (400, 0.25), (1_200, 0.65), (2_500, 1)),
        ((0, 0), (15, 0.2), (50, 0.65), (100, 1)),
        {
            "distance": 0.2,
            "elevation_gain": 0.2,
            "climbing_density": 0.15,
            "surface": 0.1,
            "steepness": 0.15,
            "trail_difficulty": 0.2,
        },
        _MTB_SURFACE,
    ),
}

STEEPNESS_SEVERITY = {
    "extreme_decline": 1.0,
    "very_steep_decline": 0.85,
    "steep_decline": 0.65,
    "moderate_decline": 0.4,
    "gentle_decline": 0.15,
    "level": 0,
    "gentle_incline": 0.15,
    "moderate_incline": 0.4,
    "steep_incline": 0.65,
    "very_steep_incline": 0.85,
    "extreme_incline": 1.0,
}
HIKING_TRAIL_SEVERITY = {
    "hiking": 0.1,
    "mountain_hiking": 0.3,
    "demanding_mountain_hiking": 0.5,
    "alpine_hiking": 0.7,
    "demanding_alpine_hiking": 0.85,
    "difficult_alpine_hiking": 1.0,
}
MOUNTAIN_BIKE_TRAIL_SEVERITY = {
    "mountain_bike_s0": 0.1,
    "mountain_bike_s1": 0.25,
    "mountain_bike_s2": 0.45,
    "mountain_bike_s3": 0.65,
    "mountain_bike_s4": 0.85,
    "mountain_bike_s5": 1.0,
}
TRAIL_SEVERITY_BY_ACTIVITY = {
    ActivityKind.HIKING: HIKING_TRAIL_SEVERITY,
    ActivityKind.MOUNTAIN_BIKING: MOUNTAIN_BIKE_TRAIL_SEVERITY,
}


def interpolate(value: float, anchors: tuple[tuple[float, float], ...]) -> float:
    """Bounded, monotonic piecewise-linear interpolation over fixed anchors."""
    if value <= anchors[0][0]:
        return anchors[0][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:], strict=False):
        if value <= x1:
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return anchors[-1][1]


def _distribution(
    entries: list[DistanceBreakdown], severity: dict[str, float], route_distance: float
) -> tuple[float | None, float]:
    weighted = known_share = 0.0
    for entry in entries:
        share = (
            entry.proportion
            if entry.proportion is not None
            else entry.distance_meters / route_distance
            if route_distance > 0
            else 0
        )
        if entry.value in severity:
            weighted += share * severity[entry.value]
            known_share += share
    return ((weighted / known_share) if known_share > 0 else None, min(known_share, 1))


def assess_route_difficulty(candidate: RouteCandidate) -> RouteDifficultyAssessment:
    """Assess one candidate without athlete, provider, batch, or external state."""
    try:
        calibration = CALIBRATIONS[candidate.activity_kind]
    except KeyError as error:
        raise UnsupportedDifficultyScoringError(
            f"No {DIFFICULTY_SCORING_VERSION} calibration for "
            f"{candidate.activity_kind.value}."
        ) from error

    values: dict[str, tuple[float | None, str, float]] = {}
    values["distance"] = (
        interpolate(candidate.distance_meters, calibration.distance_anchors),
        f"{candidate.distance_meters:.1f} meters",
        1,
    )
    elevation = candidate.elevation_gain_meters
    values["elevation_gain"] = (
        interpolate(elevation, calibration.elevation_anchors)
        if elevation is not None
        else None,
        f"{elevation:.1f} meters climbed"
        if elevation is not None
        else "elevation gain unavailable",
        1,
    )
    density = (
        elevation / (candidate.distance_meters / 1000)
        if (elevation is not None and candidate.distance_meters > 0)
        else None
    )
    values["climbing_density"] = (
        interpolate(density, calibration.climbing_density_anchors)
        if density is not None
        else None,
        f"{density:.1f} meters climbed per kilometer"
        if density is not None
        else "climbing density unavailable",
        1,
    )
    surface_score, surface_coverage = _distribution(
        candidate.surface_breakdown,
        calibration.surface_severity,
        candidate.distance_meters,
    )
    values["surface"] = (
        surface_score,
        "known surface-weighted route share",
        surface_coverage,
    )
    steep = [
        item
        for item in candidate.technical_breakdown
        if item.characteristic == "steepness"
    ]
    steep_score, steep_coverage = _distribution(
        steep, STEEPNESS_SEVERITY, candidate.distance_meters
    )
    values["steepness"] = (
        steep_score,
        "severity weighted by route share",
        steep_coverage,
    )
    if "trail_difficulty" in calibration.component_weights:
        trail = [
            item
            for item in candidate.technical_breakdown
            if item.characteristic == "trail_difficulty"
        ]
        trail_score, trail_coverage = _distribution(
            trail,
            TRAIL_SEVERITY_BY_ACTIVITY[candidate.activity_kind],
            candidate.distance_meters,
        )
        values["trail_difficulty"] = (
            trail_score,
            "activity-relevant trail severity weighted by route share",
            trail_coverage,
        )

    components = [
        ScoreComponent(
            name=name,
            score=values[name][0],
            weight=weight,
            evidence_available=values[name][0] is not None,
            evidence_summary=values[name][1],
        )
        for name, weight in calibration.component_weights.items()
    ]
    available_weight = sum(
        item.weight for item in components if item.evidence_available
    )
    score = (
        sum(item.score * item.weight for item in components if item.score is not None)
        / available_weight
    )
    coverage = sum(
        calibration.component_weights[name] * values[name][2]
        if values[name][0] is not None
        else 0
        for name in calibration.component_weights
    )
    warnings = [
        f"missing_{item.name}_evidence"
        for item in components
        if not item.evidence_available
    ]
    distribution_coverages = {
        "surface": surface_coverage,
        "steepness": steep_coverage,
    }
    if "trail_difficulty" in calibration.component_weights:
        distribution_coverages["trail_difficulty"] = trail_coverage
    warnings.extend(
        f"partial_{name}_evidence"
        for name, component_coverage in distribution_coverages.items()
        if values[name][0] is not None and component_coverage < 1
    )
    return RouteDifficultyAssessment(
        score=score,
        components=components,
        evidence_coverage=coverage,
        scoring_version=DIFFICULTY_SCORING_VERSION,
        warnings=warnings,
    )


def score_route_candidate(
    candidate: RouteCandidate,
) -> tuple[RouteCandidate, RouteDifficultyAssessment]:
    """Return a copy populated only with RouteMuse's intrinsic difficulty score."""
    assessment = assess_route_difficulty(candidate)
    return candidate.model_copy(
        update={"difficulty_score": assessment.score}
    ), assessment
