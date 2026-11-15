"""
core/interfaces/storage.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Abstract contract for the local storage engine.

The business and analysis layers must ONLY interact with storage via
this interface.  Concrete implementations (Parquet + DuckDB + SQLite)
are injected at startup; modules never import them directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import polars as pl

from core.entities import AdjustmentEvent, MarketBar, Security, Timeframe


class BaseStorageEngine(ABC):
    """
    Port definition for the local data persistence layer.

    Implementations must guarantee:
    - Atomic writes (no partial state left on failure).
    - Idempotent upserts (re-running the same batch is safe).
    - Per-symbol isolation (one symbol's failure must not corrupt others).
    """

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def initialise(self) -> None:
        """Create schema / directories / connections if not already present."""

    @abstractmethod
    async def close(self) -> None:
        """Flush buffers and close all open handles cleanly."""

    # ------------------------------------------------------------------ #
    # Security metadata
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def upsert_securities(self, securities: list[Security]) -> int:
        """
        Insert or update security metadata records.

        Returns the number of rows affected.
        """

    @abstractmethod
    async def get_security(self, symbol: str) -> Security | None:
        """Return the Security record for `symbol`, or None if not found."""

    # ------------------------------------------------------------------ #
    # Market bar data  (OHLCV)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def write_bars(
        self,
        bars: list[MarketBar],
        *,
        overwrite_existing: bool = False,
    ) -> int:
        """
        Persist a list of raw (adj_type=NONE) bars using an atomic
        staging → validate → rename commit pattern.

        Parameters
        ----------
        bars              : Bars to persist (must all share the same symbol
                            and timeframe for atomic isolation).
        overwrite_existing: If True, replace bars with matching timestamps.

        Returns
        -------
        Number of new rows written (excluding duplicates).

        Raises
        ------
        AtomicWriteError   – commit to production zone failed.
        StorageError       – any other persistence failure.
        """

    @abstractmethod
    async def read_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """
        Read raw bars for `symbol` over [start, end] (inclusive).

        Returns a Polars DataFrame with the canonical OHLCV schema.
        Returns an empty DataFrame (correct schema) when no data exists.
        """

    # ------------------------------------------------------------------ #
    # Adjustment events
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def write_adjustment_events(self, events: list[AdjustmentEvent]) -> int:
        """Persist corporate-action / adjustment events."""

    @abstractmethod
    async def read_adjustment_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[AdjustmentEvent]:
        """Return adjustment events for `symbol` in [start, end]."""

    # ------------------------------------------------------------------ #
    # Arbitrary analytical SQL (DuckDB passthrough)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def query(self, sql: str, params: dict[str, Any] | None = None) -> pl.DataFrame:
        """
        Execute a DuckDB-flavoured SQL query against the production zone.

        For analytical use only.  Write operations MUST use the typed
        methods above, never raw SQL.
        """

    # ------------------------------------------------------------------ #
    # Housekeeping
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def get_coverage(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> tuple[datetime | None, datetime | None]:
        """
        Return the (earliest, latest) timestamp available locally for
        the given symbol and timeframe.  Both are None if no data exists.
        """

    @abstractmethod
    async def verify_integrity(self, symbol: str, timeframe: Timeframe) -> bool:
        """
        Verify the on-disk file checksum and row count for the given
        symbol.  Returns True if the file is intact.
        """
