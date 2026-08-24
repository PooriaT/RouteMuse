from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class StravaAthleteDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int


class StravaTokenExchangeDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: SecretStr
    refresh_token: SecretStr
    expires_at: int
    athlete: StravaAthleteDTO


class StravaTokenRefreshDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: SecretStr
    refresh_token: SecretStr
    expires_at: int


class StravaActivityMapDTO(BaseModel):
    """Minimal map portion of a Strava SummaryActivity."""

    model_config = ConfigDict(extra="ignore")

    summary_polyline: str | None = None


class StravaActivityDTO(BaseModel):
    """Minimal SummaryActivity data needed at the import boundary."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(gt=0)
    sport_type: str = Field(min_length=1, max_length=64)
    start_date: datetime
    moving_time: int = Field(ge=0)
    distance: float = Field(ge=0)
    total_elevation_gain: float = Field(ge=0)
    map: StravaActivityMapDTO | None = None

    @field_validator("start_date")
    @classmethod
    def require_aware_start_date(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("start_date must include a timezone offset")
        return value.astimezone(UTC)
