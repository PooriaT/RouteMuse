import pytest
from pydantic import ValidationError

from app.domain.recommendations import (
    RECOMMENDATION_REASONING_SCHEMA_VERSION,
    RecommendationQualitativeTag,
    RecommendationReasoning,
)


def valid_reasoning(**changes):
    value = {
        "summary": "A grounded recommendation.",
        "reasons": [],
        "cautions": [],
        "highlights": [],
        "qualitative_tags": [],
    }
    value.update(changes)
    return value


def test_minimal_reasoning_and_schema_version() -> None:
    reasoning = RecommendationReasoning.model_validate(valid_reasoning())
    assert reasoning.summary == "A grounded recommendation."
    assert RECOMMENDATION_REASONING_SCHEMA_VERSION == "reasoning-v1"


def test_populated_reasoning_accepts_bounded_grounded_content() -> None:
    reasoning = RecommendationReasoning.model_validate(
        valid_reasoning(
            reasons=["Matches the requested challenge."],
            cautions=["Elevation evidence is unavailable."],
            highlights=["The supplied distance is 12 km."],
            qualitative_tags=[
                "close_to_target",
                "strong_athlete_fit",
                "high_climbing",
                "mixed_surface",
                "technical_terrain",
                "novel",
                "familiar",
                "limited_evidence",
            ],
        )
    )
    assert reasoning.qualitative_tags == list(RecommendationQualitativeTag)


@pytest.mark.parametrize(
    "payload",
    [
        {"reasons": [], "cautions": [], "highlights": [], "qualitative_tags": []},
        valid_reasoning(summary="   "),
        valid_reasoning(unexpected="value"),
        valid_reasoning(reasons="not a list"),
        valid_reasoning(reasons=["item"] * 9),
        valid_reasoning(highlights=["x" * 301]),
        valid_reasoning(qualitative_tags=["scenic"]),
        valid_reasoning(coordinates=[1, 2]),
        valid_reasoning(geometry={"type": "LineString"}),
    ],
)
def test_reasoning_rejects_invalid_or_unbounded_output(payload) -> None:
    with pytest.raises(ValidationError):
        RecommendationReasoning.model_validate(payload)
