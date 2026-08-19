from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "RouteMuse API"
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://routemuse:routemuse@localhost:5432/routemuse"
    )
    cors_origins: str = "http://localhost:3000"

    @property
    def allowed_origins(self) -> list[str]:
        return [
            value.strip() for value in self.cors_origins.split(",") if value.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
