from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.domain.activities import Activity
from app.domain.athlete_profile import AthleteProfile
from app.domain.planning_areas import PlanningArea
from app.domain.recommendations import RecommendationReasoning
from app.domain.routes import (
    RouteCandidate,
    RouteDiscoveryRequest,
    RoutingRequest,
    TrailFeature,
)


class ActivityProvider(Protocol):
    async def activities(self, start: date, end: date) -> list[Activity]: ...


class GeocodingProvider(Protocol):
    async def search(self, query: str, *, limit: int = 5) -> list[PlanningArea]: ...


class RouteDiscoveryProvider(Protocol):
    async def discover(self, request: RouteDiscoveryRequest) -> list[TrailFeature]: ...


class RoutingProvider(Protocol):
    async def route(self, request: RoutingRequest) -> RouteCandidate: ...


@dataclass(frozen=True)
class LlmProviderStatus:
    configured: bool
    reachable: bool
    model_available: bool
    provider: str
    model: str | None


class LlmProvider(Protocol):
    async def status(self) -> LlmProviderStatus: ...

    async def explain(
        self, candidate: RouteCandidate, athlete: AthleteProfile
    ) -> RecommendationReasoning: ...
