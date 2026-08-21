import importlib
import subprocess
import sys
from pathlib import Path

from alembic.config import Config

from app.db import models
from app.db.base import Base

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]


def test_alembic_environment_loads_without_database_connection() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND_DIRECTORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in result.stdout
    assert "CREATE TABLE strava_connections" in result.stdout
    assert "CREATE TABLE strava_activities" in result.stdout
    assert "CREATE TABLE strava_synchronization_runs" in result.stdout
    assert "uq_strava_activities_connection_activity" in result.stdout


def test_revision_chain_and_safe_postgis_downgrade() -> None:
    revision = importlib.import_module("migrations.versions.0001_enable_postgis")

    assert revision.revision == "0001"
    assert revision.down_revision is None
    assert revision.downgrade() is None


def test_strava_persistence_revision_is_importable_and_chained() -> None:
    revision = importlib.import_module(
        "migrations.versions.0002_add_strava_persistence"
    )

    assert revision.revision == "0002"
    assert revision.down_revision == "0001"


def test_alembic_configuration_defers_database_url_to_application_settings() -> None:
    config = Config(BACKEND_DIRECTORY / "alembic.ini")

    assert config.get_main_option("sqlalchemy.url") == ""


def test_model_package_uses_the_single_declarative_metadata() -> None:
    assert models is not None
    assert set(Base.metadata.tables) == {
        "strava_connections",
        "strava_activities",
        "strava_synchronization_runs",
    }
