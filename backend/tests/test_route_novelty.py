from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.activities import ActivityKind
from app.domain.history import HistoricalActivityGeometry, HistoricalGeometryHistory
from app.domain.routes import GeoJsonLineString, ProviderProvenance, RouteCandidate
from app.services.encoded_polyline import decode_summary_polyline
from app.services.geometry_cells import geometry_cells, shared_projection_origin
from app.services.route_novelty import (
    NoveltyStatus,
    assess_route_novelty,
    score_candidate_novelty,
)


def line(offset: float = 0.0, *, drift: float = 0.0) -> GeoJsonLineString:
    return GeoJsonLineString(
        coordinates=[
            [-123.1 + offset, 49.2 + drift],
            [-123.09 + offset, 49.2 + drift],
            [-123.08 + offset, 49.2 + drift],
        ]
    )


def history(*geometries: GeoJsonLineString, eligible: int | None = None):
    return HistoricalGeometryHistory(
        eligible_activity_count=eligible if eligible is not None else len(geometries),
        geometries=[
            HistoricalActivityGeometry(
                external_id=str(index),
                activity_kind=ActivityKind.HIKING,
                started_at=datetime(2026, 1, 1, tzinfo=UTC),
                geometry=geometry,
            )
            for index, geometry in enumerate(geometries)
        ],
    )


def test_known_polyline_decodes_to_canonical_longitude_latitude() -> None:
    decoded = decode_summary_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert decoded.coordinates == [
        (-120.2, 38.5),
        (-120.95, 40.7),
        (-126.453, 43.252),
    ]


@pytest.mark.parametrize("encoded", ["", "_p~iF", "?", "~~~~~~~"])
def test_malformed_or_too_short_polyline_is_rejected(encoded: str) -> None:
    with pytest.raises(ValueError):
        decode_summary_polyline(encoded)


def test_projection_origin_is_antimeridian_safe() -> None:
    geometry = GeoJsonLineString(coordinates=[(179.9, 10.0), (-179.9, 10.0)])
    _, longitude = shared_projection_origin([geometry])
    assert abs(abs(longitude) - 180) < 0.01


def test_antimeridian_line_is_continuous_when_global_history_moves_origin() -> None:
    crossing = GeoJsonLineString(
        coordinates=[(179.9, 10.0), (-179.9, 10.0), (-179.8, 10.0)]
    )
    reversed_crossing = GeoJsonLineString(
        coordinates=list(reversed(crossing.coordinates))
    )
    prime_meridian = GeoJsonLineString(coordinates=[(-0.1, 10.0), (0.1, 10.0)])
    latitude, longitude = shared_projection_origin([crossing, prime_meridian])

    crossing_cells = geometry_cells(crossing, latitude, longitude)
    reversed_cells = geometry_cells(reversed_crossing, latitude, longitude)

    # A 33 km line should not be interpreted as a 40,000 km segment, and choosing
    # its continuous branch must not depend on traversal direction.
    assert len(crossing_cells) < 10_000
    assert crossing_cells == reversed_cells


def test_global_history_does_not_break_antimeridian_novelty() -> None:
    crossing = GeoJsonLineString(
        coordinates=[(179.9, 10.0), (-179.9, 10.0), (-179.8, 10.0)]
    )
    reversed_crossing = GeoJsonLineString(
        coordinates=list(reversed(crossing.coordinates))
    )
    prime_meridian = GeoJsonLineString(coordinates=[(-0.1, 10.0), (0.1, 10.0)])

    assessment = assess_route_novelty(
        crossing, history(reversed_crossing, prime_meridian)
    )

    assert assessment.novelty_score is not None
    assert assessment.novelty_score < 0.01


def test_identical_reversed_and_drifted_routes_are_familiar() -> None:
    candidate = line()
    for historical in (
        candidate,
        GeoJsonLineString(coordinates=list(reversed(candidate.coordinates))),
        line(drift=0.0001),
    ):
        assessment = assess_route_novelty(candidate, history(historical))
        assert assessment.status is NoveltyStatus.AVAILABLE
        assert assessment.novelty_score is not None
        assert assessment.novelty_score < 0.1


def test_partial_overlap_and_distinct_route_have_expected_novelty() -> None:
    candidate = line()
    partial = GeoJsonLineString(
        coordinates=[candidate.coordinates[0], candidate.coordinates[1]]
    )
    partial_score = assess_route_novelty(candidate, history(partial)).novelty_score
    distinct_score = assess_route_novelty(
        candidate, history(line(offset=0.1))
    ).novelty_score
    assert partial_score is not None and 0.25 < partial_score < 0.75
    assert distinct_score is not None and distinct_score > 0.95


def test_no_geometry_is_explicitly_insufficient_not_novel() -> None:
    assessment = assess_route_novelty(line(), history(eligible=4))
    assert assessment.status is NoveltyStatus.INSUFFICIENT_HISTORY
    assert assessment.novelty_score is None
    assert assessment.confidence == 0
    assert assessment.geometry_coverage_ratio == 0
    assert assessment.missing_geometry_activity_count == 4


def test_confidence_combines_coverage_and_amount_and_only_updates_novelty() -> None:
    evidence = history(*([line()] * 5), eligible=10)
    candidate = RouteCandidate(
        id=uuid4(),
        name="candidate",
        activity_kind=ActivityKind.ROAD_CYCLING,
        distance_meters=2_000.0,
        geometry=line(),
        provenance=[ProviderProvenance(provider="test", attribution="test")],
        difficulty_score=0.4,
        athlete_fit_score=0.6,
    )
    scored, assessment = score_candidate_novelty(candidate, evidence)
    assert assessment.confidence == 0.25
    assert scored.novelty_score is not None
    assert scored.difficulty_score == 0.4
    assert scored.athlete_fit_score == 0.6
    assert scored.confidence_score is None
