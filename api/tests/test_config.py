"""Settings contract: the 14 keys of .env.example (docs/PROMPTS.md:50)."""

from app.config import Settings

ENV_KEYS = [
    "database_url",
    "github_token",
    "openai_api_key",
    "openai_model",
    "openai_model_fallback",
    "max_files",
    "max_file_mb",
    "max_total_mb",
    "daily_limit_per_ip",
    "rate_limit_bypass_ips",
    "domain",
    "fallback_domain",
    "acme_email",
    "s3_bucket",
]


def test_settings_defines_exactly_the_14_env_keys():
    assert sorted(Settings.model_fields) == sorted(ENV_KEYS)


def test_settings_defaults_match_env_example():
    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://postgres:postgres@db:5432/repodoc"
    assert settings.max_files == 3000
    assert settings.max_file_mb == 5
    assert settings.max_total_mb == 300
    assert settings.daily_limit_per_ip == 100
    assert settings.github_token == ""
    assert settings.s3_bucket == ""


def test_settings_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("MAX_FILES", "7")
    monkeypatch.setenv("MAX_FILE_MB", "2")

    settings = Settings(_env_file=None)

    assert settings.max_files == 7
    assert settings.max_file_mb == 2
