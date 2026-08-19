import subprocess
import sys
from pathlib import Path


def test_alembic_environment_loads_without_database_connection() -> None:
    backend_directory = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=backend_directory,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in result.stdout
