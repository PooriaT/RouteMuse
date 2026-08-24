from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_name: str = "RouteMuse API"
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://routemuse:routemuse@localhost:5432/routemuse"
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    frontend_url: str = "http://localhost:3000"
    strava_client_id: str | None = None
    strava_client_secret: SecretStr | None = None
    strava_redirect_uri: str | None = None
    strava_token_encryption_key: SecretStr | None = None
    openrouteservice_api_key: SecretStr | None = None
    overpass_api_url: str = "https://overpass-api.de/api/interpreter"
    overpass_user_agent: str = "RouteMuse/0.1 (OpenStreetMap discovery)"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated environment value or an explicit list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("frontend_url")
    @classmethod
    def validate_frontend_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "frontend_url must be an HTTP(S) URL without credentials, "
                "query, or fragment"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
