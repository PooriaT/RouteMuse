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
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    ollama_request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

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

    @field_validator("ollama_base_url", mode="before")
    @classmethod
    def validate_ollama_base_url(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            return None
        try:
            parsed = urlsplit(value)
            valid_port = parsed.port
        except ValueError as exc:
            raise ValueError("ollama_base_url must be a valid HTTP(S) URL") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or valid_port is not None
            and not 1 <= valid_port <= 65535
        ):
            raise ValueError(
                "ollama_base_url must be an HTTP(S) URL without credentials, "
                "query, or fragment"
            )
        value = value.rstrip("/")
        return value[:-4] if value.endswith("/api") else value

    @field_validator("ollama_model", mode="before")
    @classmethod
    def normalize_ollama_model(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
