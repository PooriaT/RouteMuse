"""Pure, deterministic excitement scoring from defensible route evidence."""

from dataclasses import dataclass
from math import log

from app.domain.activities import ActivityKind
from app.domain.recommendations import ExcitementAssessment, ExcitementComponent
from app.domain.routes import DistanceBreakdown, RouteCandidate, TrailFeature
from app.services.geometry_cells import geometry_cells, shared_projection_origin
from app.services.route_novelty import NoveltyAssessment, NoveltyStatus

EXCITEMENT_SCORING_VERSION = "excitement-v1"
MINIMUM_EVIDENCE_COVERAGE = 0.35
MATERIAL_OVERLAP_MINIMUM = 0.02
VARIETY_CATEGORY_CAP = 4
UNKNOWN_VALUES = {"unknown", "unrated", "unspecified", "unclassified", "other"}
UNKNOWN_VALUE_PREFIXES = ("unknown_",)

# Shape is deliberately small. Differences between activities are restrained and
# encode only which kinds have a stronger factual basis for terrain/surface variety.
ACTIVITY_WEIGHTS: dict[ActivityKind, dict[str, float]] = {
    ActivityKind.WALKING: {
        "novelty": 0.25,
        "surface_variety": 0.17,
        "way_type_variety": 0.18,
        "terrain_variety": 0.12,
        "named_content": 0.20,
        "route_shape": 0.08,
    },
    ActivityKind.HIKING: {
        "novelty": 0.24,
        "surface_variety": 0.15,
        "way_type_variety": 0.13,
        "terrain_variety": 0.20,
        "named_content": 0.20,
        "route_shape": 0.08,
    },
    ActivityKind.ROAD_CYCLING: {
        "novelty": 0.25,
        "surface_variety": 0.10,
        "way_type_variety": 0.22,
        "terrain_variety": 0.15,
        "named_content": 0.20,
        "route_shape": 0.08,
    },
    ActivityKind.GRAVEL_CYCLING: {
        "novelty": 0.24,
        "surface_variety": 0.21,
        "way_type_variety": 0.16,
        "terrain_variety": 0.15,
        "named_content": 0.16,
        "route_shape": 0.08,
    },
    ActivityKind.MOUNTAIN_BIKING: {
        "novelty": 0.22,
        "surface_variety": 0.16,
        "way_type_variety": 0.13,
        "terrain_variety": 0.23,
        "named_content": 0.18,
        "route_shape": 0.08,
    },
}


class UnsupportedExcitementScoringError(ValueError):
    """The activity has no reviewed excitement weight table."""


@dataclass(frozen=True)
class NamedFeatureOverlap:
    """Factual named content materially intersecting the candidate."""

    features: tuple[TrailFeature, ...]
    overlapping_named_feature_count: int
    overlapping_named_route_count: int
    approximate_named_route_coverage: float


def _shares(
    entries: list[DistanceBreakdown], distance: float
) -> tuple[dict[str, float], float]:
    shares: dict[str, float] = {}
    for entry in entries:
        value = entry.value.strip().lower()
        # ORS preserves unmapped provider codes as ``unknown_<code>`` and uses
        # ``unrated`` for technical code zero. Neither is a factual category.
        if value in UNKNOWN_VALUES or value.startswith(UNKNOWN_VALUE_PREFIXES):
            continue
        share = (
            entry.proportion
            if entry.proportion is not None
            else (entry.distance_meters or 0) / distance
            if distance
            else 0
        )
        if share > 0:
            shares[value] = shares.get(value, 0) + share
    return shares, min(sum(shares.values()), 1.0)


def distribution_variety(
    entries: list[DistanceBreakdown], route_distance: float
) -> tuple[float | None, float]:
    """Return capped normalized Shannon entropy and known route-share coverage."""
    shares, coverage = _shares(entries, route_distance)
    total = sum(shares.values())
    if not total:
        return None, 0.0
    entropy = -sum((share / total) * log(share / total) for share in shares.values())
    return min(entropy / log(VARIETY_CATEGORY_CAP), 1.0), coverage


def overlapping_named_features(
    candidate: RouteCandidate, features: list[TrailFeature]
) -> NamedFeatureOverlap:
    """Match named ways/relations by shared route cells, never planning-box presence."""
    geometries = [candidate.geometry, *(feature.geometry for feature in features)]
    latitude, longitude = shared_projection_origin(geometries)
    candidate_cells = geometry_cells(candidate.geometry, latitude, longitude)
    accepted: list[TrailFeature] = []
    covered: set[tuple[int, int]] = set()
    route_ids: set[str] = set()
    feature_names: set[str] = set()
    for feature in features:
        if feature.name is None and not feature.named_route_memberships:
            continue
        overlap = candidate_cells & geometry_cells(
            feature.geometry, latitude, longitude
        )
        if len(overlap) / len(candidate_cells) < MATERIAL_OVERLAP_MINIMUM:
            continue
        accepted.append(feature)
        covered.update(overlap)
        if feature.name is not None:
            feature_names.add(feature.name)
        route_ids.update(route.source_id for route in feature.named_route_memberships)
    return NamedFeatureOverlap(
        tuple(accepted),
        len(feature_names),
        len(route_ids),
        min(len(covered) / len(candidate_cells), 1.0),
    )


def assess_route_excitement(
    candidate: RouteCandidate,
    novelty: NoveltyAssessment | None = None,
    trail_features: list[TrailFeature] | None = None,
) -> ExcitementAssessment:
    """Assess excitement without providers, difficulty, preferences, or mutation."""
    try:
        weights = ACTIVITY_WEIGHTS[candidate.activity_kind]
    except KeyError as error:
        raise UnsupportedExcitementScoringError(
            f"No {EXCITEMENT_SCORING_VERSION} weights for "
            f"{candidate.activity_kind.value}."
        ) from error

    values: dict[str, tuple[float | None, float, str]] = {}
    novelty_score = (
        novelty.novelty_score
        if novelty and novelty.status is NoveltyStatus.AVAILABLE
        else None
    )
    values["novelty"] = (
        novelty_score,
        novelty.confidence if novelty_score is not None else 0,
        f"geographic novelty {novelty_score:.3f}"
        if novelty_score is not None
        else "novelty unavailable",
    )
    for name, entries in (
        ("surface_variety", candidate.surface_breakdown),
        ("way_type_variety", candidate.way_type_breakdown),
    ):
        score, coverage = distribution_variety(entries, candidate.distance_meters)
        values[name] = (
            score,
            coverage,
            "proportion-aware diversity across "
            f"{len(_shares(entries, candidate.distance_meters)[0])} known categories"
            if score is not None
            else "distribution unavailable",
        )
    technical_scores: list[tuple[float, float, str]] = []
    for characteristic in ("steepness", "trail_difficulty"):
        entries = [
            item
            for item in candidate.technical_breakdown
            if item.characteristic == characteristic
        ]
        score, coverage = distribution_variety(entries, candidate.distance_meters)
        if score is not None:
            technical_scores.append((score, coverage, characteristic))
    values["terrain_variety"] = (
        (sum(item[0] for item in technical_scores) / len(technical_scores))
        if technical_scores
        else None,
        (sum(item[1] for item in technical_scores) / len(technical_scores))
        if technical_scores
        else 0,
        "variety across " + ", ".join(item[2] for item in technical_scores)
        if technical_scores
        else "technical distributions unavailable",
    )
    if trail_features is None:
        values["named_content"] = (None, 0, "trail discovery context unavailable")
    else:
        overlap = overlapping_named_features(candidate, trail_features)
        score = min(
            0.7 * overlap.approximate_named_route_coverage
            + 0.15 * min(overlap.overlapping_named_feature_count, 2)
            + 0.15 * min(overlap.overlapping_named_route_count, 2),
            1.0,
        )
        values["named_content"] = (
            score,
            1,
            f"{overlap.overlapping_named_feature_count} named features, "
            f"{overlap.overlapping_named_route_count} named routes, "
            f"{overlap.approximate_named_route_coverage:.1%} approximate coverage",
        )
    shape_scores = {"loop": 0.7, "out_and_back": 0.45, "point_to_point": 0.5}
    shape_score = (
        shape_scores.get(candidate.route_shape.value) if candidate.route_shape else None
    )
    values["route_shape"] = (
        shape_score,
        1 if shape_score is not None else 0,
        f"route shape: {candidate.route_shape.value}"
        if candidate.route_shape
        else "route shape unavailable",
    )

    components = [
        ExcitementComponent(
            name=name,
            score=values[name][0],
            base_weight=weight,
            evidence_available=values[name][0] is not None,
            evidence_summary=values[name][2],
        )
        for name, weight in weights.items()
    ]
    available_weight = sum(
        item.base_weight for item in components if item.evidence_available
    )
    coverage = sum(weights[name] * values[name][1] for name in weights)
    score = (
        sum(
            item.score * item.base_weight
            for item in components
            if item.score is not None
        )
        / available_weight
        if coverage >= MINIMUM_EVIDENCE_COVERAGE and available_weight
        else None
    )
    warnings = [
        f"missing_{item.name}_evidence"
        for item in components
        if not item.evidence_available
    ]
    if score is None:
        warnings.append("insufficient_excitement_evidence")
    return ExcitementAssessment(
        score=score,
        components=components,
        evidence_coverage=coverage,
        scoring_version=EXCITEMENT_SCORING_VERSION,
        warnings=warnings,
    )


def score_candidate_excitement(
    candidate: RouteCandidate,
    novelty: NoveltyAssessment | None = None,
    trail_features: list[TrailFeature] | None = None,
) -> tuple[RouteCandidate, ExcitementAssessment]:
    assessment = assess_route_excitement(candidate, novelty, trail_features)
    return candidate.model_copy(
        update={"excitement_score": assessment.score}
    ), assessment
