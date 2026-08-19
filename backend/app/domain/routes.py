from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.activities import ActivityKind


class RouteShape(StrEnum):
    LOOP = "loop"
    OUT_AND_BACK = "out_and_back"
    POINT_TO_POINT = "point_to_point"


class RouteCandidate(BaseModel):
    """Provider-backed facts and optional deterministic recommendation outputs."""

    id: UUID
    name: str
    activity_kind: ActivityKind
    distance_meters: float = Field(ge=0)
    estimated_duration_seconds: int | None = Field(default=None, ge=0)
    elevation_gain_meters: float | None = Field(default=None, ge=0)
    geometry: dict[str, Any] | None = None
    geojson_reference: str | None = None
    route_shape: RouteShape | None = None
    surfaces: list[str] = Field(default_factory=list)
    technical_attributes: dict[str, Any] = Field(default_factory=dict)
    source_provider: str
    source_attribution: str
    difficulty_score: float | None = Field(default=None, ge=0, le=1)
    athlete_fit_score: float | None = Field(default=None, ge=0, le=1)
    excitement_score: float | None = Field(default=None, ge=0, le=1)
    novelty_score: float | None = Field(default=None, ge=0, le=1)
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    explanation: str | None = None
    warnings: list[str] = Field(default_factory=list)
