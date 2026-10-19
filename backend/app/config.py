from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if parsed < minimum or (maximum is not None and parsed > maximum):
        return default
    return parsed


@dataclass(frozen=True)
class Settings:
    storage_dir: Path
    session_ttl_seconds: int = 3600
    keep_last_n: int = 3
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pages: int = 5
    rate_limit_per_minute: int = 60
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        storage_value = os.getenv("PRIVASHIELD_STORAGE_DIR")
        storage_dir = Path(storage_value) if storage_value else Path(tempfile.gettempdir()) / "privashield-sessions"
        cors_value = os.getenv("PRIVASHIELD_CORS_ORIGINS")
        origins = tuple(item.strip() for item in cors_value.split(",") if item.strip()) if cors_value else cls.cors_origins
        return cls(
            storage_dir=storage_dir,
            session_ttl_seconds=_positive_int("PRIVASHIELD_SESSION_TTL_SECONDS", 3600, 60),
            keep_last_n=_positive_int("PRIVASHIELD_KEEP_LAST_N", 3, 1, 20),
            rate_limit_per_minute=_positive_int("PRIVASHIELD_RATE_LIMIT_PER_MINUTE", 60, 1, 1000),
            cors_origins=origins,
        )
