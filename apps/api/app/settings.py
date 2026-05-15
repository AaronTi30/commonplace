from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str | None = None

    upload_dir: str = "~/.commonplace/uploads"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "mistral"
    ollama_timeout_seconds: float = 120.0

    def resolved_upload_dir(self) -> str:
        return os.path.expanduser(self.upload_dir)


settings = Settings()

