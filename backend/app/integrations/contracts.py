from datetime import date
from typing import Protocol

from app.domain.activities import Activity
from app.domain.athlete_profile import AthleteProfile
from app.domain.recommendations import RecommendationExplanation
from app.domain.routes import RouteCandidate


class ActivityProvider(Protocol):
    async def activities(self, start: date, end: date) -> list[Activity]: ...


class GeocodingProvider(Protocol):
    async def geocode(self, query: str) -> tuple[float, float] | None: ...


class RouteDiscoveryProvider(Protocol):
    async def discover(
        self, latitude: float, longitude: float
    ) -> list[RouteCandidate]: ...


class RoutingProvider(Protocol):
    async def route(self, waypoints: list[tuple[float, float]]) -> RouteCandidate: ...


class LlmProvider(Protocol):
    async def explain(
        self, candidate: RouteCandidate, athlete: AthleteProfile
    ) -> RecommendationExplanation: ...
