"""
storage/sqlite_meta.py
~~~~~~~~~~~~~~~~~~~~~~
Asynchronous SQLite metadata and state management with WAL mode and
automated on-disk reconciliation recovery.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from core.entities import (
    AdjustmentEvent,
    AssetType,
    DataRevisionRecord,
    ListingStatus,
    Market,
    RawResponseArchive,
    Security,
    Timeframe,
)
from storage.parquet_manager import (
    ParquetStorageManager,
    calculate_file_checksums,
    infer_market_from_symbol,
)

logger = logging.getLogger(__name__)


class SQLiteMetadataManager:
    """Manages securities, adjustment events, and coverage metadata in SQLite."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Establish connection and initialize tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        # Enable WAL mode and normal synchronous for fast concurrent reads and safety
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._conn.execute("PRAGMA synchronous = NORMAL;")
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._init_schema()

    async def close(self) -> None:
        """Close connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database connection is not open. Call connect() first.")
        return self._conn

    async def _init_schema(self) -> None:
        """Create tables if not already existing."""
        async with self.conn.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS securities (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    listing_status TEXT NOT NULL,
                    listed_date TEXT,
                    delisted_date TEXT,
                    currency TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS adjustment_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    ex_date TEXT NOT NULL,
                    cash_dividend REAL NOT NULL,
                    bonus_ratio REAL NOT NULL,
                    rights_ratio REAL NOT NULL,
                    rights_price REAL NOT NULL,
                    source_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(symbol, ex_date, cash_dividend, bonus_ratio)
                );
                """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bar_coverage (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    market TEXT NOT NULL,
                    start_date TEXT,
                    end_date TEXT,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    file_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    quality_status TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, timeframe)
                );
                """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_response_audit (
                    id TEXT PRIMARY KEY,
                    provider_name TEXT NOT NULL,
                    source_interface TEXT NOT NULL,
                    request_ts TEXT NOT NULL,
                    request_params TEXT NOT NULL,
                    response_status TEXT NOT NULL,
                    response_ts TEXT NOT NULL,
                    raw_response_hash TEXT NOT NULL,
                    normalized_data_hash TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    raw_payload_path TEXT,
                    transformation_version TEXT NOT NULL
                );
                """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS data_revision_audit (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    revised_ts_count INTEGER NOT NULL,
                    sample_diffs TEXT NOT NULL,
                    old_fingerprint TEXT NOT NULL,
                    new_fingerprint TEXT NOT NULL,
                    revised_at TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS acquisition_tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    total_symbols INTEGER NOT NULL,
                    completed_symbols INTEGER NOT NULL DEFAULT 0,
                    failed_symbols INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    last_heartbeat_at TEXT,
                    error_message TEXT,
                    params_json TEXT
                );
                """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS acquisition_task_items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    row_count INTEGER DEFAULT 0,
                    provider_used TEXT,
                    source_interface TEXT,
                    execution_latency_ms REAL,
                    error_message TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    FOREIGN KEY(task_id) REFERENCES acquisition_tasks(task_id) ON DELETE CASCADE
                );
                """
            )
            await cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_adj_symbol ON adjustment_events(symbol);"
            )
            await cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_audit_symbol ON raw_response_audit(symbol);"
            )
            await cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_audit_hash "
                "ON raw_response_audit(raw_response_hash);"
            )
            await cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_rev_audit_symbol ON data_revision_audit(symbol);"
            )
            await cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_acq_task_status ON acquisition_tasks(status);"
            )
            await cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_acq_task_heartbeat "
                "ON acquisition_tasks(last_heartbeat_at);"
            )
            await cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_acq_item_task_symbol "
                "ON acquisition_task_items(task_id, symbol);"
            )
            await cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_acq_item_status ON acquisition_task_items(status);"
            )
        await self.conn.commit()

    # ------------------------------------------------------------------ #
    # Securities
    # ------------------------------------------------------------------ #

    async def upsert_securities(self, securities: list[Security]) -> int:
        """Insert or update security records."""
        if not securities:
            return 0
        now_str = datetime.now(UTC).isoformat()
        records = [
            (
                s.symbol,
                s.name,
                s.market.value,
                s.asset_type.value,
                s.listing_status.value,
                s.listed_date.isoformat() if s.listed_date else None,
                s.delisted_date.isoformat() if s.delisted_date else None,
                s.currency,
                now_str,
            )
            for s in securities
        ]
        sql = """
            INSERT INTO securities (
                symbol, name, market, asset_type, listing_status,
                listed_date, delisted_date, currency, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = excluded.name,
                market = excluded.market,
                asset_type = excluded.asset_type,
                listing_status = excluded.listing_status,
                listed_date = excluded.listed_date,
                delisted_date = excluded.delisted_date,
                currency = excluded.currency,
                updated_at = excluded.updated_at;
        """
        async with self.conn.cursor() as cur:
            await cur.executemany(sql, records)
        await self.conn.commit()
        return len(records)

    async def get_security(self, symbol: str) -> Security | None:
        """Fetch Security record by canonical symbol."""
        sql = """
            SELECT symbol, name, market, asset_type, listing_status,
                   listed_date, delisted_date, currency
            FROM securities WHERE symbol = ?
        """
        async with self.conn.execute(sql, (symbol.upper().strip(),)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return Security(
                symbol=row[0],
                name=row[1],
                market=Market(row[2]),
                asset_type=AssetType(row[3]),
                listing_status=ListingStatus(row[4]),
                listed_date=datetime.fromisoformat(row[5]) if row[5] else None,
                delisted_date=datetime.fromisoformat(row[6]) if row[6] else None,
                currency=row[7],
            )

    # ------------------------------------------------------------------ #
    # Adjustment Events
    # ------------------------------------------------------------------ #

    async def upsert_adjustment_events(self, events: list[AdjustmentEvent]) -> int:
        """Insert adjustment events ignoring existing duplicates."""
        if not events:
            return 0
        now_str = datetime.now(UTC).isoformat()
        records = [
            (
                ev.symbol,
                ev.ex_date.isoformat(),
                ev.cash_dividend,
                ev.bonus_ratio,
                ev.rights_ratio,
                ev.rights_price,
                ev.source_id,
                now_str,
            )
            for ev in events
        ]
        sql = """
            INSERT OR IGNORE INTO adjustment_events (
                symbol, ex_date, cash_dividend, bonus_ratio,
                rights_ratio, rights_price, source_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        async with self.conn.cursor() as cur:
            await cur.executemany(sql, records)
        await self.conn.commit()
        return len(records)

    async def get_adjustment_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[AdjustmentEvent]:
        """Fetch adjustment events for `symbol` within [start, end]."""
        sql = """
            SELECT symbol, ex_date, cash_dividend, bonus_ratio,
                   rights_ratio, rights_price, source_id
            FROM adjustment_events
            WHERE symbol = ? AND ex_date >= ? AND ex_date <= ?
            ORDER BY ex_date ASC
        """
        async with self.conn.execute(
            sql, (symbol.upper().strip(), start.isoformat(), end.isoformat())
        ) as cur:
            rows = await cur.fetchall()
            return [
                AdjustmentEvent(
                    symbol=r[0],
                    ex_date=datetime.fromisoformat(r[1]),
                    cash_dividend=r[2],
                    bonus_ratio=r[3],
                    rights_ratio=r[4],
                    rights_price=r[5],
                    source_id=r[6],
                )
                for r in rows
            ]

    # ------------------------------------------------------------------ #
    # Coverage & State
    # ------------------------------------------------------------------ #

    async def update_coverage(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_date: datetime | None,
        end_date: datetime | None,
        row_count: int,
        file_path: Path,
        file_hash: str,
        quality_status: str = "PASS",
    ) -> None:
        """Update or insert bar coverage entry."""
        market = infer_market_from_symbol(symbol)
        now_str = datetime.now(UTC).isoformat()
        sql = """
            INSERT INTO bar_coverage (
                symbol, timeframe, market, start_date, end_date,
                row_count, file_path, file_hash, quality_status, last_updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe) DO UPDATE SET
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                row_count = excluded.row_count,
                file_path = excluded.file_path,
                file_hash = excluded.file_hash,
                quality_status = excluded.quality_status,
                last_updated_at = excluded.last_updated_at;
        """
        params = (
            symbol.upper().strip(),
            timeframe.value,
            market.value,
            start_date.isoformat() if start_date else None,
            end_date.isoformat() if end_date else None,
            row_count,
            str(file_path),
            file_hash,
            quality_status,
            now_str,
        )
        async with self.conn.cursor() as cur:
            await cur.execute(sql, params)
        await self.conn.commit()

    async def get_coverage(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> tuple[datetime | None, datetime | None]:
        """Return (earliest, latest) timestamp recorded in SQLite."""
        sql = "SELECT start_date, end_date FROM bar_coverage WHERE symbol = ? AND timeframe = ?"
        async with self.conn.execute(sql, (symbol.upper().strip(), timeframe.value)) as cur:
            row = await cur.fetchone()
            if not row or not row[0] or not row[1]:
                return None, None
            return datetime.fromisoformat(row[0]), datetime.fromisoformat(row[1])

    # ------------------------------------------------------------------ #
    # Crash Recovery & Reconciliation
    # ------------------------------------------------------------------ #

    async def reconcile_with_disk(self, parquet_manager: ParquetStorageManager) -> dict[str, int]:
        """
        Reconcile SQLite metadata with physical on-disk Parquet files.
        Recovers from unexpected process crashes between Parquet write
        and SQLite commit.
        """
        import polars as pl

        reconciled_count = 0
        deleted_orphans_count = 0

        # 1. Clean up dangling .tmp files
        cleaned_tmp = parquet_manager.cleanup_temp_files()

        # 2. Scan physical production files
        for p in parquet_manager.production_dir.rglob("*.parquet"):
            symbol = p.stem.upper().strip()
            # Try to get timeframe from parent directory or default to 1d
            tf_str = p.parent.name
            try:
                timeframe = Timeframe(tf_str)
            except ValueError:
                timeframe = Timeframe.D1

            try:
                df = pl.read_parquet(p)
                row_count = len(df)
                start_date: datetime | None = None
                end_date: datetime | None = None
                if row_count > 0:
                    min_val = df["ts"].min()
                    max_val = df["ts"].max()
                    if isinstance(min_val, datetime):
                        start_date = min_val
                    if isinstance(max_val, datetime):
                        end_date = max_val

                _, file_hash = calculate_file_checksums(p)
                await self.update_coverage(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    row_count=row_count,
                    file_path=p,
                    file_hash=file_hash,
                    quality_status="PASS",
                )
                reconciled_count += 1
            except Exception as e:
                logger.warning("Error reading parquet file %s during reconciliation: %s", p, e)

        # 3. Check for orphaned records in SQLite pointing to non-existent files
        async with self.conn.execute(
            "SELECT symbol, timeframe, file_path FROM bar_coverage"
        ) as cur:
            records = await cur.fetchall()

        for sym, tf, fpath in records:
            if not Path(fpath).exists():
                await self.conn.execute(
                    "DELETE FROM bar_coverage WHERE symbol = ? AND timeframe = ?", (sym, tf)
                )
                deleted_orphans_count += 1

        await self.conn.commit()
        return {
            "reconciled_files": reconciled_count,
            "deleted_orphans": deleted_orphans_count,
            "cleaned_temp_files": cleaned_tmp,
        }

    # ------------------------------------------------------------------ #
    # Raw Response Provenance & Data Revision Audit (Step6)
    # ------------------------------------------------------------------ #

    async def insert_raw_response_archive(self, archive: RawResponseArchive) -> None:
        """Persist a raw external response provenance archive record."""
        sql = """
        INSERT INTO raw_response_audit (
            id, provider_name, source_interface, request_ts, request_params,
            response_status, response_ts, raw_response_hash, normalized_data_hash,
            symbol, market, row_count, raw_payload_path, transformation_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            archive.id,
            archive.provider_name,
            archive.source_interface,
            archive.request_ts.isoformat(),
            json.dumps(archive.request_params),
            archive.response_status,
            archive.response_ts.isoformat(),
            archive.raw_response_hash,
            archive.normalized_data_hash,
            archive.symbol,
            archive.market.value,
            archive.row_count,
            archive.raw_payload_path,
            archive.transformation_version,
        )
        await self.conn.execute(sql, params)
        await self.conn.commit()

    async def get_raw_response_archives(
        self, symbol: str, limit: int = 50
    ) -> list[RawResponseArchive]:
        """Query raw response archive records for a symbol."""
        sql = """
        SELECT id, provider_name, source_interface, request_ts, request_params,
               response_status, response_ts, raw_response_hash, normalized_data_hash,
               symbol, market, row_count, raw_payload_path, transformation_version
        FROM raw_response_audit
        WHERE symbol = ?
        ORDER BY response_ts DESC
        LIMIT ?;
        """
        archives: list[RawResponseArchive] = []
        async with self.conn.execute(sql, (symbol, limit)) as cur:
            rows = await cur.fetchall()
            for r in rows:
                archives.append(
                    RawResponseArchive(
                        id=r[0],
                        provider_name=r[1],
                        source_interface=r[2],
                        request_ts=datetime.fromisoformat(r[3]),
                        request_params=json.loads(r[4]) if r[4] else {},
                        response_status=r[5],
                        response_ts=datetime.fromisoformat(r[6]),
                        raw_response_hash=r[7],
                        normalized_data_hash=r[8],
                        symbol=r[9],
                        market=Market(r[10]),
                        row_count=r[11],
                        raw_payload_path=r[12] or "",
                        transformation_version=r[13],
                    )
                )
        return archives

    async def insert_data_revision_record(self, record: DataRevisionRecord) -> None:
        """Persist a historical data revision / retrospective update record."""
        sql = """
        INSERT INTO data_revision_audit (
            id, symbol, timeframe, revised_ts_count, sample_diffs,
            old_fingerprint, new_fingerprint, revised_at, reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            record.id,
            record.symbol,
            record.timeframe.value,
            record.revised_ts_count,
            json.dumps(record.sample_diffs),
            record.old_fingerprint,
            record.new_fingerprint,
            record.revised_at.isoformat(),
            record.reason,
        )
        await self.conn.execute(sql, params)
        await self.conn.commit()

    async def get_data_revision_records(
        self, symbol: str, limit: int = 50
    ) -> list[DataRevisionRecord]:
        """Query historical data revision audit records for a symbol."""
        sql = """
        SELECT id, symbol, timeframe, revised_ts_count, sample_diffs,
               old_fingerprint, new_fingerprint, revised_at, reason
        FROM data_revision_audit
        WHERE symbol = ?
        ORDER BY revised_at DESC
        LIMIT ?;
        """
        records: list[DataRevisionRecord] = []
        async with self.conn.execute(sql, (symbol, limit)) as cur:
            rows = await cur.fetchall()
            for r in rows:
                records.append(
                    DataRevisionRecord(
                        id=r[0],
                        symbol=r[1],
                        timeframe=Timeframe(r[2]),
                        revised_ts_count=r[3],
                        sample_diffs=json.loads(r[4]) if r[4] else [],
                        old_fingerprint=r[5],
                        new_fingerprint=r[6],
                        revised_at=datetime.fromisoformat(r[7]),
                        reason=r[8],
                    )
                )
        return records

    # ------------------------------------------------------------------ #
    # Acquisition Task Persistence & Zombie Detection (Directive 1 & 5)
    # ------------------------------------------------------------------ #

    async def create_acquisition_task(
        self,
        task_id: str,
        symbols: list[str],
        timeframe: str,
        start_date: str,
        end_date: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Create a new acquisition master task and its constituent symbol items."""
        now_str = datetime.now(UTC).isoformat()
        sql_task = """
        INSERT INTO acquisition_tasks (
            task_id, status, symbols_json, timeframe, start_date, end_date,
            total_symbols, completed_symbols, failed_symbols, created_at,
            last_heartbeat_at, params_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?);
        """
        params_json = json.dumps(params or {})
        await self.conn.execute(
            sql_task,
            (
                task_id,
                "PENDING",
                json.dumps(symbols),
                timeframe,
                start_date,
                end_date,
                len(symbols),
                now_str,
                now_str,
                params_json,
            ),
        )

        sql_item = """
        INSERT INTO acquisition_task_items (
            task_id, symbol, status
        ) VALUES (?, ?, 'PENDING');
        """
        for sym in symbols:
            await self.conn.execute(sql_item, (task_id, sym.upper().strip()))

        await self.conn.commit()

    async def get_acquisition_task(self, task_id: str) -> dict[str, Any] | None:
        """Query acquisition master task details."""
        sql = """
        SELECT task_id, status, symbols_json, timeframe, start_date, end_date,
               total_symbols, completed_symbols, failed_symbols, created_at,
               started_at, finished_at, last_heartbeat_at, error_message, params_json
        FROM acquisition_tasks
        WHERE task_id = ?;
        """
        async with self.conn.execute(sql, (task_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "task_id": row[0],
                "status": row[1],
                "symbols": json.loads(row[2]),
                "timeframe": row[3],
                "start_date": row[4],
                "end_date": row[5],
                "total_symbols": row[6],
                "completed_symbols": row[7],
                "failed_symbols": row[8],
                "created_at": row[9],
                "started_at": row[10],
                "finished_at": row[11],
                "last_heartbeat_at": row[12],
                "error_message": row[13],
                "params": json.loads(row[14]) if row[14] else {},
            }

    async def list_acquisition_tasks(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List acquisition master tasks with optional status filter."""
        args: tuple[Any, ...]
        if status:
            sql = """
            SELECT task_id, status, symbols_json, timeframe, start_date, end_date,
                   total_symbols, completed_symbols, failed_symbols, created_at,
                   started_at, finished_at, last_heartbeat_at, error_message, params_json
            FROM acquisition_tasks
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?;
            """
            args = (status.upper(), limit, offset)
        else:
            sql = """
            SELECT task_id, status, symbols_json, timeframe, start_date, end_date,
                   total_symbols, completed_symbols, failed_symbols, created_at,
                   started_at, finished_at, last_heartbeat_at, error_message, params_json
            FROM acquisition_tasks
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?;
            """
            args = (limit, offset)

        tasks: list[dict[str, Any]] = []
        async with self.conn.execute(sql, args) as cur:
            rows = await cur.fetchall()
            for row in rows:
                tasks.append(
                    {
                        "task_id": row[0],
                        "status": row[1],
                        "symbols": json.loads(row[2]),
                        "timeframe": row[3],
                        "start_date": row[4],
                        "end_date": row[5],
                        "total_symbols": row[6],
                        "completed_symbols": row[7],
                        "failed_symbols": row[8],
                        "created_at": row[9],
                        "started_at": row[10],
                        "finished_at": row[11],
                        "last_heartbeat_at": row[12],
                        "error_message": row[13],
                        "params": json.loads(row[14]) if row[14] else {},
                    }
                )
        return tasks

    async def update_acquisition_task_heartbeat(self, task_id: str) -> None:
        """Update last_heartbeat_at for a running task."""
        now_str = datetime.now(UTC).isoformat()
        sql = """
        UPDATE acquisition_tasks
        SET last_heartbeat_at = ?
        WHERE task_id = ?;
        """
        await self.conn.execute(sql, (now_str, task_id))
        await self.conn.commit()

    async def update_acquisition_task_status(
        self,
        task_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Update master task status and lifecycle timestamps."""
        now_str = datetime.now(UTC).isoformat()
        if status.upper() == "RUNNING":
            sql = """
            UPDATE acquisition_tasks
            SET status = ?, started_at = COALESCE(started_at, ?), last_heartbeat_at = ?
            WHERE task_id = ?;
            """
            await self.conn.execute(sql, (status.upper(), now_str, now_str, task_id))
        elif status.upper() in ("SUCCESS", "PARTIAL_SUCCESS", "FAILED", "CANCELLED", "INTERRUPTED"):
            sql = """
            UPDATE acquisition_tasks
            SET status = ?, finished_at = ?, error_message = COALESCE(?, error_message),
                last_heartbeat_at = ?
            WHERE task_id = ?;
            """
            await self.conn.execute(sql, (status.upper(), now_str, error_message, now_str, task_id))
        else:
            sql = "UPDATE acquisition_tasks SET status = ? WHERE task_id = ?;"
            await self.conn.execute(sql, (status.upper(), task_id))
        await self.conn.commit()

    async def update_acquisition_task_item(
        self,
        task_id: str,
        symbol: str,
        status: str,
        row_count: int = 0,
        provider_used: str | None = None,
        source_interface: str | None = None,
        latency_ms: float | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update individual symbol item status and refresh parent task counts."""
        now_str = datetime.now(UTC).isoformat()
        sql_item = """
        UPDATE acquisition_task_items
        SET status = ?,
            row_count = ?,
            provider_used = ?,
            source_interface = ?,
            execution_latency_ms = ?,
            error_message = ?,
            finished_at = ?
        WHERE task_id = ? AND symbol = ?;
        """
        await self.conn.execute(
            sql_item,
            (
                status.upper(),
                row_count,
                provider_used,
                source_interface,
                latency_ms,
                error_message,
                now_str,
                task_id,
                symbol.upper().strip(),
            ),
        )

        # Refresh aggregated counts on parent task
        sql_count = """
        UPDATE acquisition_tasks
        SET completed_symbols = (
                SELECT COUNT(*) FROM acquisition_task_items
                WHERE task_id = ? AND status = 'SUCCESS'
            ),
            failed_symbols = (
                SELECT COUNT(*) FROM acquisition_task_items
                WHERE task_id = ? AND status = 'FAILED'
            ),
            last_heartbeat_at = ?
        WHERE task_id = ?;
        """
        await self.conn.execute(sql_count, (task_id, task_id, now_str, task_id))
        await self.conn.commit()

    async def get_acquisition_task_items(self, task_id: str) -> list[dict[str, Any]]:
        """Get all symbol items for an acquisition task."""
        sql = """
        SELECT item_id, symbol, status, row_count, provider_used,
               source_interface, execution_latency_ms, error_message,
               started_at, finished_at
        FROM acquisition_task_items
        WHERE task_id = ?
        ORDER BY item_id ASC;
        """
        items: list[dict[str, Any]] = []
        async with self.conn.execute(sql, (task_id,)) as cur:
            rows = await cur.fetchall()
            for r in rows:
                items.append(
                    {
                        "item_id": r[0],
                        "symbol": r[1],
                        "status": r[2],
                        "row_count": r[3],
                        "provider_used": r[4],
                        "source_interface": r[5],
                        "execution_latency_ms": r[6],
                        "error_message": r[7],
                        "started_at": r[8],
                        "finished_at": r[9],
                    }
                )
        return items

    async def cleanup_zombie_tasks(self, timeout_seconds: float = 120.0) -> int:
        """
        Directive 1: Detect and mark zombie tasks that have been in RUNNING state
        without a heartbeat for more than timeout_seconds.
        """
        now = datetime.now(UTC)
        threshold_dt = now - timedelta(seconds=timeout_seconds)
        threshold_iso = threshold_dt.isoformat()

        # Find running tasks with stale heartbeat
        sql_find = """
        SELECT task_id FROM acquisition_tasks
        WHERE status = 'RUNNING' AND last_heartbeat_at < ?;
        """
        zombies: list[str] = []
        async with self.conn.execute(sql_find, (threshold_iso,)) as cur:
            rows = await cur.fetchall()
            zombies = [r[0] for r in rows]

        if not zombies:
            return 0

        now_str = now.isoformat()
        err = (
            f"Marked as INTERRUPTED: Heartbeat stale for > {timeout_seconds}s "
            "(process failure or zombie)"
        )
        for tid in zombies:
            await self.conn.execute(
                """
                UPDATE acquisition_tasks
                SET status = 'INTERRUPTED', error_message = ?, finished_at = ?
                WHERE task_id = ?;
                """,
                (err, now_str, tid),
            )
            await self.conn.execute(
                """
                UPDATE acquisition_task_items
                SET status = 'INTERRUPTED', error_message = ?
                WHERE task_id = ? AND status = 'RUNNING';
                """,
                (err, tid),
            )

        await self.conn.commit()
        return len(zombies)
