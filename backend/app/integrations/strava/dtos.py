from pydantic import BaseModel, ConfigDict, SecretStr


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
