"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sovren Backend"
    database_url: str = "sqlite+aiosqlite:///sovren.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

