from dataclasses import dataclass

from app.domain.activities import Activity, ActivityKind
from app.integrations.strava.dtos import StravaActivityDTO

STRAVA_SPORT_TYPE_TO_ACTIVITY_KIND: dict[str, ActivityKind] = {
    "Walk": ActivityKind.WALKING,
    "Run": ActivityKind.RUNNING,
    "TrailRun": ActivityKind.TRAIL_RUNNING,
    "Hike": ActivityKind.HIKING,
    "Ride": ActivityKind.ROAD_CYCLING,
    "GravelRide": ActivityKind.GRAVEL_CYCLING,
    "MountainBikeRide": ActivityKind.MOUNTAIN_BIKING,
    "AlpineSki": ActivityKind.ALPINE_SKIING,
    "BackcountrySki": ActivityKind.BACKCOUNTRY_SKIING,
    "NordicSki": ActivityKind.NORDIC_SKIING,
}


@dataclass(frozen=True, slots=True)
class NormalizedStravaSportType:
    """Exact provider value and its optional RouteMuse classification."""

    source_sport_type: str
    activity_kind: ActivityKind | None


@dataclass(frozen=True, slots=True)
class StravaActivityNormalizationResult:
    """Normalization outcome without inventing an activity for unsupported sports."""

    source_sport_type: str
    activity_kind: ActivityKind | None
    activity: Activity | None


def normalize_strava_sport_type(sport_type: str) -> NormalizedStravaSportType:
    """Translate one exact Strava API sport type into the RouteMuse taxonomy."""

    return NormalizedStravaSportType(
        source_sport_type=sport_type,
        activity_kind=STRAVA_SPORT_TYPE_TO_ACTIVITY_KIND.get(sport_type),
    )


def normalize_strava_activity(
    source: StravaActivityDTO,
) -> StravaActivityNormalizationResult:
    """Normalize supported provider data while retaining unsupported sport types."""

    normalized_sport_type = normalize_strava_sport_type(source.sport_type)
    activity_kind = normalized_sport_type.activity_kind
    if activity_kind is None:
        return StravaActivityNormalizationResult(
            source_sport_type=source.sport_type,
            activity_kind=None,
            activity=None,
        )

    return StravaActivityNormalizationResult(
        source_sport_type=source.sport_type,
        activity_kind=activity_kind,
        activity=Activity(
            external_id=str(source.id),
            kind=activity_kind,
            started_at=source.start_date,
            moving_time_seconds=source.moving_time,
            distance_meters=source.distance,
            elevation_gain_meters=source.total_elevation_gain,
        ),
    )
