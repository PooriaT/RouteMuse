from types import SimpleNamespace

import pytest

from app.domain.reasoning_context import RecommendationReasoningContext
from app.domain.recommendations import (
    RankedRecommendation,
    ReasoningSource,
    RecommendationReasoning,
)
from app.integrations.llm.errors import LlmTimeoutError
from app.services import recommendation_reasoning as service


def context(**updates) -> RecommendationReasoningContext:
    payload = {
        "recommendation": {
            "rank": 1,
            "final_score": 0.82,
            "ranking_version": "recommendation-v1",
        },
        "planning_preferences": {
            "activity_kind": "hiking",
            "target_distance_meters": 10000,
            "target_duration_seconds": None,
            "desired_challenge": "moderate",
            "route_shape": "loop",
            "novelty_preference": "novel",
            "planning_area_display_name": "Test",
        },
        "athlete": {
            "activity_kind": "hiking",
            "matching_activity_sample_count": 5,
            "distance_meters": None,
            "moving_time_seconds": None,
            "elevation_gain_meters": None,
            "elevation_gain_meters_per_km": None,
            "consistency": None,
        },
        "route_facts": {
            "name": "Route",
            "activity_kind": "hiking",
            "distance_meters": 10000,
            "estimated_duration_seconds": None,
            "elevation_gain_meters": 420,
            "elevation_loss_meters": None,
            "route_shape": "loop",
            "data_confidence": 0.8,
            "surfaces": [],
            "way_types": [],
            "technical_characteristics": [],
            "provenance": [],
        },
        "scorecard": {
            "difficulty": 0.6,
            "athlete_fit": 0.8,
            "athlete_fit_status": "scored",
            "novelty": {
                "status": "available",
                "score": 0.75,
                "confidence": 0.8,
                "geometry_coverage_ratio": 0.8,
            },
            "excitement": 0.6,
            "preference_alignment": 0.9,
            "confidence": 0.7,
            "final_score": 0.82,
            "components": [
                {
                    "component": "preference_alignment.target_distance",
                    "score": 0.9,
                    "evidence_available": True,
                    "evidence_summary": "distance evidence",
                },
                {
                    "component": "preference_alignment.desired_challenge",
                    "score": 0.85,
                    "evidence_available": True,
                    "evidence_summary": "challenge evidence",
                },
            ],
        },
        "evidence_limitations": {
            "warnings": ["candidate_warning"],
            "strings_truncated": False,
            "collections_truncated": False,
        },
    }
    for section, values in updates.items():
        payload[section].update(values)
    return RecommendationReasoningContext.model_validate(payload)


def test_fallback_is_exact_and_deterministic():
    first = service.build_deterministic_reasoning(context())
    assert first == service.build_deterministic_reasoning(context())
    assert (
        first.summary
        == "Rank 1 hiking route: 10.0 km and 420 m elevation gain; athlete-fit 0.80."
    )
    assert first.reasons == [
        "Athlete-fit score is 0.80.",
        "Requested-preference alignment score is 0.90.",
        "moderate challenge alignment score is 0.85.",
        "Novelty score is 0.75 for the requested novel preference.",
    ]
    assert first.cautions == ["candidate_warning"]
    assert first.highlights == [
        "Route distance: 10.0 km.",
        "Elevation gain: 420 m.",
        "Route shape: loop.",
        "Known novelty score: 0.75.",
    ]
    assert [tag.value for tag in first.qualitative_tags] == [
        "close_to_target",
        "strong_athlete_fit",
        "novel",
        "limited_evidence",
    ]


def test_missing_elevation_and_novelty_are_not_highlights():
    value = context(
        route_facts={"elevation_gain_meters": None},
        scorecard={
            "novelty": {
                "status": "insufficient_history",
                "score": None,
                "confidence": 0,
                "geometry_coverage_ratio": 0,
            }
        },
    )
    result = service.build_deterministic_reasoning(value)
    assert not any(
        "Elevation" in item or "novelty score" in item for item in result.highlights
    )
    assert "Novelty is unavailable from the supplied history." in result.cautions


class FailingProvider:
    def __init__(self):
        self.calls = 0

    async def explain(self, context):
        self.calls += 1
        raise LlmTimeoutError()


@pytest.mark.anyio
async def test_first_provider_failure_disables_remaining_calls(monkeypatch):
    monkeypatch.setattr(service, "build_reasoning_context", lambda *args: context())
    provider = FailingProvider()
    ranked = [RankedRecommendation.model_construct(rank=i) for i in range(1, 4)]
    enriched, warnings = await service.enrich_recommendations(
        ranked, SimpleNamespace(), SimpleNamespace(), provider
    )
    assert provider.calls == 1
    assert warnings == ["ollama_timeout_using_fallback"]
    assert all(
        item.reasoning.source is ReasoningSource.DETERMINISTIC_FALLBACK
        for item in enriched
    )
    assert [item.rank for item in enriched] == [1, 2, 3]


class SuccessfulProvider:
    def __init__(self):
        self.calls = 0

    async def explain(self, context):
        self.calls += 1
        return RecommendationReasoning(
            summary="distance evidence",
            reasons=[],
            cautions=[],
            highlights=[],
            qualitative_tags=[],
        )


@pytest.mark.anyio
async def test_success_is_sequentially_bounded_by_selected_count(monkeypatch):
    monkeypatch.setattr(service, "build_reasoning_context", lambda *args: context())
    provider = SuccessfulProvider()
    ranked = [
        RankedRecommendation.model_construct(rank=i, final_score=0.5)
        for i in range(1, 3)
    ]
    enriched, warnings = await service.enrich_recommendations(
        ranked, SimpleNamespace(), SimpleNamespace(), provider, model="test-model"
    )
    assert provider.calls == len(ranked)
    assert warnings == []
    assert all(item.reasoning.source is ReasoningSource.OLLAMA for item in enriched)
    assert [(item.rank, item.final_score) for item in enriched] == [(1, 0.5), (2, 0.5)]
