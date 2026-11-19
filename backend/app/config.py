"""Runtime configuration, read once from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))
    gemini_fallback_models: list[str] = field(
        default_factory=lambda: _csv(os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-2.5-flash"))
    )
    waqi_token: str = field(default_factory=lambda: os.getenv("WAQI_TOKEN", ""))
    allowed_origins: list[str] = field(
        default_factory=lambda: _csv(os.getenv("ALLOWED_ORIGINS", "http://localhost:5173"))
    )
    database_path: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_PATH", str(Path(__file__).resolve().parent.parent / "data" / "breathewise.db")
        )
    )
    static_dir: str = field(
        default_factory=lambda: os.getenv(
            "STATIC_DIR", str(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist")
        )
    )
    air_cache_seconds: int = field(default_factory=lambda: int(os.getenv("AIR_CACHE_SECONDS", "600")))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")))
    ai_rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("AI_RATE_LIMIT_PER_MINUTE", "12"))
    )

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key)


settings = Settings()
