from app.core.config import Settings


def test_configuration_loading(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test API")
    monkeypatch.setenv("CORS_ORIGINS", "http://one.test, http://two.test")
    settings = Settings(_env_file=None)
    assert settings.app_name == "Test API"
    assert settings.cors_origins == ["http://one.test", "http://two.test"]


def test_configuration_accepts_an_explicit_cors_origin_list() -> None:
    settings = Settings(cors_origins=["https://app.example.com"], _env_file=None)
    assert settings.cors_origins == ["https://app.example.com"]


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
