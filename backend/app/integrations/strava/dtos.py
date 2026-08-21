from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr


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


class StravaActivityDTO(BaseModel):
    """Minimal SummaryActivity data needed at the import boundary."""

    model_config = ConfigDict(extra="ignore")

    id: int
    sport_type: str
    start_date: datetime
    moving_time: int = Field(ge=0)
    distance: float = Field(ge=0)
    total_elevation_gain: float = Field(ge=0)
