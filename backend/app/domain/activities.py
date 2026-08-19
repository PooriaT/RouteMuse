from enum import StrEnum


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
