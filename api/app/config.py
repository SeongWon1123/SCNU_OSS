"""Application settings — the 14-key contract of .env.example (docs/PROMPTS.md:50)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/repodoc"
    github_token: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    openai_model_fallback: str = ""
    max_files: int = 3000
    max_file_mb: int = 5
    max_total_mb: int = 300
    daily_limit_per_ip: int = 100
    rate_limit_bypass_ips: str = ""
    domain: str = ""
    fallback_domain: str = ""
    acme_email: str = ""
    s3_bucket: str = ""
