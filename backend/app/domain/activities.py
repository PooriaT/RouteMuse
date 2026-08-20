from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ActivityKind(StrEnum):
    """RouteMuse-owned activity taxonomy, independent of providers."""

    WALKING = "walking"
    RUNNING = "running"
    TRAIL_RUNNING = "trail_running"
    HIKING = "hiking"
    ROAD_CYCLING = "road_cycling"
    GRAVEL_CYCLING = "gravel_cycling"
    MOUNTAIN_BIKING = "mountain_biking"
    ALPINE_SKIING = "alpine_skiing"
    BACKCOUNTRY_SKIING = "backcountry_skiing"
    NORDIC_SKIING = "nordic_skiing"


class Activity(BaseModel):
    """A normalized RouteMuse activity produced at a provider boundary."""

    external_id: str
    kind: ActivityKind
    started_at: datetime
    moving_time_seconds: int = Field(ge=0)
    distance_meters: float = Field(ge=0)
    elevation_gain_meters: float | None = Field(default=None, ge=0)
