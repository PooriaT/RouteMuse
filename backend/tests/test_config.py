import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_configuration_loading(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test API")
    monkeypatch.setenv("CORS_ORIGINS", "http://one.test, http://two.test")
    monkeypatch.setenv("FRONTEND_URL", "https://planner.example.com/route-planner")
    settings = Settings(_env_file=None)
    assert settings.app_name == "Test API"
    assert settings.cors_origins == ["http://one.test", "http://two.test"]
    assert settings.frontend_url == "https://planner.example.com/route-planner"


def test_configuration_accepts_an_explicit_cors_origin_list() -> None:
    settings = Settings(cors_origins=["https://app.example.com"], _env_file=None)
    assert settings.cors_origins == ["https://app.example.com"]


@pytest.mark.parametrize(
    "frontend_url",
    [
        "javascript:alert(1)",
        "https://user:password@app.example.com",
        "https://app.example.com?code=oauth-code",
        "https://app.example.com#access-token",
    ],
)
def test_frontend_url_rejects_unsafe_redirect_targets(frontend_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(frontend_url=frontend_url, _env_file=None)


def test_strava_token_encryption_key_is_optional_but_secret(monkeypatch) -> None:
    monkeypatch.setenv("STRAVA_TOKEN_ENCRYPTION_KEY", "configured-secret-key")

    settings = Settings(_env_file=None)

    assert settings.strava_token_encryption_key is not None
    assert settings.strava_token_encryption_key.get_secret_value() == (
        "configured-secret-key"
    )
    assert "configured-secret-key" not in repr(settings)


def test_strava_oauth_settings_are_optional_and_client_secret_is_protected(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRAVA_CLIENT_ID", "12345")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "oauth-client-secret")
    monkeypatch.setenv(
        "STRAVA_REDIRECT_URI", "http://localhost:8000/api/v1/strava/callback"
    )

    settings = Settings(_env_file=None)

    assert settings.strava_client_id == "12345"
    assert settings.strava_client_secret is not None
    assert settings.strava_client_secret.get_secret_value() == "oauth-client-secret"
    assert settings.strava_redirect_uri == (
        "http://localhost:8000/api/v1/strava/callback"
    )
    assert "oauth-client-secret" not in repr(settings)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:11434/", "http://localhost:11434"),
        ("http://ollama.internal:11434/base///", "http://ollama.internal:11434/base"),
        ("https://models.example.com", "https://models.example.com"),
    ],
)
def test_ollama_url_is_validated_and_normalized(url: str, expected: str) -> None:
    assert Settings(ollama_base_url=url, _env_file=None).ollama_base_url == expected


@pytest.mark.parametrize(
    "url",
    [
        "localhost:11434",
        "ftp://localhost/model",
        "http://user:secret@localhost:11434",
        "http://localhost:11434?token=secret",
        "http://localhost:11434#fragment",
        "http://localhost:99999",
    ],
)
def test_ollama_url_rejects_unsafe_or_malformed_values(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(ollama_base_url=url, _env_file=None)


def test_blank_ollama_configuration_is_unconfigured() -> None:
    settings = Settings(ollama_base_url="  ", ollama_model=" \t ", _env_file=None)
    assert settings.ollama_base_url is None
    assert settings.ollama_model is None
