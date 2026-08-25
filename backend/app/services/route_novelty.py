"""Deterministic geographic novelty scoring from historical route geometry."""

from app.domain.history import HistoricalGeometryHistory
from app.domain.recommendations import NoveltyAssessment, NoveltyStatus
from app.domain.routes import GeoJsonLineString, RouteCandidate
from app.services.geometry_cells import geometry_cells, shared_projection_origin

FULL_HISTORY_EVIDENCE_ACTIVITIES = 10


def assess_route_novelty(
    candidate: GeoJsonLineString, history: HistoricalGeometryHistory
) -> NoveltyAssessment:
    count = history.geometry_activity_count
    coverage = history.geometry_coverage_ratio
    common = dict(
        eligible_activity_count=history.eligible_activity_count,
        geometry_activity_count=count,
        missing_geometry_activity_count=history.missing_geometry_activity_count,
        geometry_coverage_ratio=coverage,
    )
    if not count:
        return NoveltyAssessment(
            status=NoveltyStatus.INSUFFICIENT_HISTORY,
            novelty_score=None,
            confidence=0.0,
            **common,
        )
    geometries = [candidate, *(item.geometry for item in history.geometries)]
    latitude, longitude = shared_projection_origin(geometries)
    candidate_cells = geometry_cells(candidate, latitude, longitude)
    history_cells: set[tuple[int, int]] = set()
    for item in history.geometries:
        history_cells.update(geometry_cells(item.geometry, latitude, longitude))
    visited_fraction = len(candidate_cells & history_cells) / len(candidate_cells)
    confidence = coverage * min(count / FULL_HISTORY_EVIDENCE_ACTIVITIES, 1.0)
    return NoveltyAssessment(
        status=NoveltyStatus.AVAILABLE,
        novelty_score=max(0.0, min(1.0, 1.0 - visited_fraction)),
        confidence=confidence,
        **common,
    )


def score_candidate_novelty(
    candidate: RouteCandidate, history: HistoricalGeometryHistory
) -> tuple[RouteCandidate, NoveltyAssessment]:
    assessment = assess_route_novelty(candidate.geometry, history)
    return (
        candidate.model_copy(update={"novelty_score": assessment.novelty_score}),
        assessment,
    )
