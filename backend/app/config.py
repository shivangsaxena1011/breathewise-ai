"""Runtime configuration, read once from environment variables."""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _voter_salt() -> str:
    """Secret key for hashing voter IPs. A public default would let anyone holding the store
    brute-force the whole IPv4 space back to IPs, so without VOTER_SALT we derive one from a secret
    that every serverless instance shares, or fall back to a random per-process key."""
    if explicit := os.getenv("VOTER_SALT"):
        return explicit
    shared_secret = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("GEMINI_API_KEY")
    if shared_secret:
        return hashlib.sha256(f"breathewise-voter-salt:{shared_secret}".encode()).hexdigest()
    return secrets.token_hex(32)


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""), repr=False)
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))
    gemini_fallback_models: list[str] = field(
        default_factory=lambda: _csv(os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-2.5-flash"))
    )
    # Upstash Redis (Vercel's Marketplace integration sets the KV_* names; Upstash's own uses UPSTASH_*)
    redis_url: str = field(default_factory=lambda: os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "")
    redis_token: str = field(
        default_factory=lambda: os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or "", repr=False
    )
    voter_salt: str = field(default_factory=_voter_salt, repr=False)
    waqi_token: str = field(default_factory=lambda: os.getenv("WAQI_TOKEN", ""), repr=False)
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
    gemini_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("GEMINI_TIMEOUT_SECONDS", "20")))
    air_cache_seconds: int = field(default_factory=lambda: int(os.getenv("AIR_CACHE_SECONDS", "600")))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")))
    ai_rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("AI_RATE_LIMIT_PER_MINUTE", "12"))
    )

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key)


settings = Settings()
