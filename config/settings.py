"""
Market Insight Engine – Application Settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Loaded from environment variables or a .env file.
All modules should import `get_settings()` rather than reading os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from .env / environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="MIE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ------------------------------------------------------------------ #
    # Server
    # ------------------------------------------------------------------ #
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)

    # ------------------------------------------------------------------ #
    # Data Storage
    # ------------------------------------------------------------------ #
    data_root: Path = Path("./data")
    meta_db_path: Path | None = None  # Defaults to data_root / "meta.db" if None

    @field_validator("data_root", mode="before")
    @classmethod
    def resolve_data_root(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve()

    @property
    def meta_db(self) -> Path:
        if self.meta_db_path:
            return self.meta_db_path.expanduser().resolve()
        return self.data_root / "meta.db"

    @property
    def raw_dir(self) -> Path:
        return self.data_root / "raw"

    @property
    def staging_dir(self) -> Path:
        return self.data_root / "staging"

    @property
    def production_dir(self) -> Path:
        return self.data_root / "production"

    @property
    def quarantine_dir(self) -> Path:
        return self.data_root / "quarantine"

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #
    cache_max_size: int = Field(default=256, ge=1)
    cache_ttl_seconds: int = Field(default=300, ge=0)

    # ------------------------------------------------------------------ #
    # Hardware / Resource Limits
    # ------------------------------------------------------------------ #
    max_worker_threads: int = Field(default=4, ge=0)
    max_cpu_percent: float = Field(default=75.0, ge=10.0, le=100.0)
    enable_gpu: bool = False

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def ensure_data_dirs(self) -> None:
        """Create all data subdirectories if they do not already exist."""
        for d in (
            self.raw_dir,
            self.staging_dir,
            self.production_dir,
            self.quarantine_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def is_development(self) -> bool:
        return self.env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
