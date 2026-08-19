from datetime import date
from typing import Any, Protocol

from app.domain.athlete_profile import AthleteProfile
from app.domain.routes import RouteCandidate


class ActivityProvider(Protocol):
    async def activities(self, start: date, end: date) -> list[dict[str, Any]]: ...


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
    ) -> dict[str, Any]: ...
