from app.core.config import Settings


def test_configuration_loading(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test API")
    monkeypatch.setenv("CORS_ORIGINS", "http://one.test, http://two.test")
    settings = Settings(_env_file=None)
    assert settings.app_name == "Test API"
    assert settings.allowed_origins == ["http://one.test", "http://two.test"]
