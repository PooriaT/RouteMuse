from pydantic import BaseModel, ConfigDict, SecretStr


class StravaAthleteDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int


class StravaTokenExchangeDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: SecretStr
    refresh_token: SecretStr
    expires_at: int
    scope: str
    athlete: StravaAthleteDTO


class StravaTokenRefreshDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: SecretStr
    refresh_token: SecretStr
    expires_at: int
