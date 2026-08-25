"""Provider-neutral historical geographic evidence."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.activities import ActivityKind
from app.domain.routes import GeoJsonLineString


@dataclass(frozen=True, slots=True)
class HistoricalActivityGeometry:
    external_id: str
    activity_kind: ActivityKind | None
    started_at: datetime
    geometry: GeoJsonLineString


@dataclass(frozen=True, slots=True)
class HistoricalGeometryHistory:
    eligible_activity_count: int
    geometries: list[HistoricalActivityGeometry]

    @property
    def geometry_activity_count(self) -> int:
        return len(self.geometries)

    @property
    def missing_geometry_activity_count(self) -> int:
        return self.eligible_activity_count - self.geometry_activity_count

    @property
    def geometry_coverage_ratio(self) -> float:
        if not self.eligible_activity_count:
            return 0.0
        return self.geometry_activity_count / self.eligible_activity_count
