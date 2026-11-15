"""
storage/composite_engine.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Concrete implementation of BaseStorageEngine unifying Parquet, DuckDB,
and SQLite WAL metadata with atomic commits and crash recovery.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from config import get_settings
from core.entities import (
    AdjustmentEvent,
    DataRevisionRecord,
    MarketBar,
    RawResponseArchive,
    Security,
    Timeframe,
)
from core.exceptions import StorageError
from core.interfaces.storage import BaseStorageEngine
from storage.duckdb_engine import DuckDBEngine
from storage.parquet_manager import ParquetStorageManager
from storage.sqlite_meta import SQLiteMetadataManager

logger = logging.getLogger(__name__)


class CompositeStorageEngine(BaseStorageEngine):
    """
    Local storage engine orchestrator combining:
    - ParquetStorageManager: for raw OHLCV bar storage with atomic commit semantics.
    - DuckDBEngine: for analytical OLAP SQL queries.
    - SQLiteMetadataManager: for ACID metadata, state, and crash recovery.
    """

    def __init__(
        self,
        data_root: Path | None = None,
        meta_db_path: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.data_root = data_root or settings.data_root
        self.production_dir = self.data_root / "production"
        self.staging_dir = self.data_root / "staging"
        self.quarantine_dir = self.data_root / "quarantine"
        self.raw_dir = self.data_root / "raw"
        self.meta_db_path = meta_db_path or (self.data_root / "meta.db")

        self.parquet = ParquetStorageManager(
            production_dir=self.production_dir,
            staging_dir=self.staging_dir,
            quarantine_dir=self.quarantine_dir,
        )
        self.sqlite = SQLiteMetadataManager(db_path=self.meta_db_path)
        self.duckdb = DuckDBEngine(production_dir=self.production_dir)
        self._initialised = False
        self._post_write_callbacks: list[Callable[[str, Timeframe], None]] = []

    def register_post_write_callback(self, callback: Callable[[str, Timeframe], None]) -> None:
        """Register a callback to be notified when market bars are committed to storage."""
        self._post_write_callbacks.append(callback)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def initialise(self) -> None:
        """Create directory structure and initialize storage connections."""
        for d in [
            self.data_root,
            self.production_dir,
            self.staging_dir,
            self.quarantine_dir,
            self.raw_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        await self.sqlite.connect()
        self.duckdb.connect()
        # Clean up any leftover temporary files from previous aborted runs
        self.parquet.cleanup_temp_files()
        self._initialised = True

    async def close(self) -> None:
        """Close storage connections cleanly."""
        if self._initialised:
            self.duckdb.close()
            await self.sqlite.close()
            self._initialised = False

    # ------------------------------------------------------------------ #
    # Security metadata
    # ------------------------------------------------------------------ #

    async def upsert_securities(self, securities: list[Security]) -> int:
        return await self.sqlite.upsert_securities(securities)

    async def get_security(self, symbol: str) -> Security | None:
        return await self.sqlite.get_security(symbol)

    # ------------------------------------------------------------------ #
    # Market bar data (OHLCV)
    # ------------------------------------------------------------------ #

    async def write_bars(
        self,
        bars: list[MarketBar],
        *,
        overwrite_existing: bool = False,
    ) -> int:
        """
        Atomically persist bars to Parquet and update SQLite coverage metadata.
        Guarantees per-symbol isolation.
        """
        if not bars:
            return 0

        symbol = bars[0].symbol.upper().strip()
        timeframe = bars[0].timeframe

        # Verify batch homogeneity
        for b in bars:
            if b.symbol.upper().strip() != symbol or b.timeframe != timeframe:
                raise StorageError(
                    f"write_bars requires all bars in batch to share symbol and timeframe, "
                    f"got {b.symbol} vs {symbol} and {b.timeframe} vs {timeframe}"
                )

        # 1. Atomic write to Parquet
        new_rows_count, file_hash, file_path = self.parquet.write_bars_atomic(
            bars=bars,
            timeframe=timeframe,
            overwrite_existing=overwrite_existing,
        )

        # 2. Update SQLite metadata
        existing_start, existing_end = await self.sqlite.get_coverage(symbol, timeframe)
        batch_start = min(b.ts for b in bars)
        batch_end = max(b.ts for b in bars)

        merged_start = (
            min(existing_start, batch_start) if existing_start is not None else batch_start
        )
        merged_end = max(existing_end, batch_end) if existing_end is not None else batch_end

        # Read total rows from written Parquet to have exact count
        try:
            total_rows = len(self.parquet.read_bars(symbol, timeframe, merged_start, merged_end))
        except Exception:
            total_rows = new_rows_count

        await self.sqlite.update_coverage(
            symbol=symbol,
            timeframe=timeframe,
            start_date=merged_start,
            end_date=merged_end,
            row_count=total_rows,
            file_path=file_path,
            file_hash=file_hash,
            quality_status="PASS",
        )

        # Record revision audit if historical modifications were detected
        if self.parquet.last_detected_revision:
            await self.sqlite.insert_data_revision_record(self.parquet.last_detected_revision)

        # Notify post-write listeners (e.g. invalidate in-memory API and indicator caches)
        for cb in self._post_write_callbacks:
            try:
                cb(symbol, timeframe)
            except Exception as cb_err:
                logger.warning("Post-write callback error for %s: %s", symbol, cb_err)

        return new_rows_count

    async def read_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """Read raw bars for symbol over [start, end]."""
        return self.parquet.read_bars(
            symbol=symbol.upper().strip(),
            timeframe=timeframe,
            start=start,
            end=end,
        )

    # ------------------------------------------------------------------ #
    # Adjustment Events
    # ------------------------------------------------------------------ #

    async def write_adjustment_events(self, events: list[AdjustmentEvent]) -> int:
        return await self.sqlite.upsert_adjustment_events(events)

    async def read_adjustment_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[AdjustmentEvent]:
        return await self.sqlite.get_adjustment_events(
            symbol=symbol.upper().strip(),
            start=start,
            end=end,
        )

    # ------------------------------------------------------------------ #
    # Analytical SQL Queries
    # ------------------------------------------------------------------ #

    async def query(self, sql: str, params: dict[str, Any] | None = None) -> pl.DataFrame:
        return await self.duckdb.query(sql, params)

    # ------------------------------------------------------------------ #
    # Housekeeping & Verification
    # ------------------------------------------------------------------ #

    async def get_coverage(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> tuple[datetime | None, datetime | None]:
        return await self.sqlite.get_coverage(symbol.upper().strip(), timeframe)

    async def verify_integrity(self, symbol: str, timeframe: Timeframe) -> bool:
        return self.parquet.verify_file_integrity(symbol.upper().strip(), timeframe)

    async def reconcile_recovery(self) -> dict[str, int]:
        """Trigger automated reconciliation between SQLite metadata and physical Parquet files."""
        return await self.sqlite.reconcile_with_disk(self.parquet)

    # ------------------------------------------------------------------ #
    # Provenance Archival & Data Revision Records (Step6)
    # ------------------------------------------------------------------ #

    async def record_raw_archive(self, archive: RawResponseArchive) -> None:
        """Persist a raw response provenance archive in SQLite."""
        await self.sqlite.insert_raw_response_archive(archive)

    async def get_raw_archives(self, symbol: str, limit: int = 50) -> list[RawResponseArchive]:
        """Retrieve raw response provenance records for a symbol."""
        return await self.sqlite.get_raw_response_archives(symbol.upper().strip(), limit)

    async def record_data_revision(self, record: DataRevisionRecord) -> None:
        """Persist a data revision record in SQLite."""
        await self.sqlite.insert_data_revision_record(record)

    async def get_data_revisions(self, symbol: str, limit: int = 50) -> list[DataRevisionRecord]:
        """Retrieve historical data revision records for a symbol."""
        return await self.sqlite.get_data_revision_records(symbol.upper().strip(), limit)
