from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    llm_provider: Literal["anthropic", "openai", "mock"] = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = "claude-3-5-sonnet-20241022"
    llm_max_tokens: int = 1024

    datastore_backend: Literal["dbus", "mock", "file"] = "mock"
    datastore_file_path: str = "./sample_journal"

    cors_origins: list[str] = ["*"]
    log_level: str = "info"


settings = Settings()
