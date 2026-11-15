"""
tests/unit/test_storage.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for ParquetStorageManager, SQLiteMetadataManager, DuckDBEngine,
and CompositeStorageEngine.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from core.entities import (
    AdjustmentEvent,
    AdjustType,
    AssetType,
    DataQualityReport,
    DataQualityStatus,
    ListingStatus,
    Market,
    MarketBar,
    Security,
    Timeframe,
)
from storage.composite_engine import CompositeStorageEngine
from storage.duckdb_engine import DuckDBEngine
from storage.parquet_manager import ParquetStorageManager
from storage.sqlite_meta import SQLiteMetadataManager


def make_bar(
    symbol: str = "600519.SH",
    ts: datetime | None = None,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: float = 1000.0,
    amount: float = 102000.0,
) -> MarketBar:
    if ts is None:
        ts = datetime(2024, 1, 2, tzinfo=UTC)
    return MarketBar(
        symbol=symbol,
        timeframe=Timeframe.D1,
        adj_type=AdjustType.NONE,
        ts=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        amount=amount,
        source_id="test",
    )


@pytest.fixture
def temp_dirs() -> tuple[Path, Path, Path, Path]:
    tmp = Path(tempfile.mkdtemp())
    prod = tmp / "production"
    stag = tmp / "staging"
    quar = tmp / "quarantine"
    raw = tmp / "raw"
    for d in [prod, stag, quar, raw]:
        d.mkdir(parents=True, exist_ok=True)
    return prod, stag, quar, raw


def test_parquet_atomic_write_and_read(temp_dirs: tuple[Path, Path, Path, Path]) -> None:
    prod, stag, quar, _ = temp_dirs
    pm = ParquetStorageManager(production_dir=prod, staging_dir=stag, quarantine_dir=quar)

    bars = [
        make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC), close=100.0),
        make_bar(ts=datetime(2024, 1, 3, tzinfo=UTC), close=102.0),
    ]

    rows, sha256_hash, final_path = pm.write_bars_atomic(bars, Timeframe.D1)
    assert rows == 2
    assert len(sha256_hash) == 64
    assert final_path.exists()
    assert pm.verify_file_integrity("600519.SH", Timeframe.D1) is True

    # Read back
    df = pm.read_bars(
        "600519.SH",
        Timeframe.D1,
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 4, tzinfo=UTC),
    )
    assert len(df) == 2
    assert df["close"].to_list() == [100.0, 102.0]


def test_parquet_upsert_overwrite(temp_dirs: tuple[Path, Path, Path, Path]) -> None:
    prod, stag, quar, _ = temp_dirs
    pm = ParquetStorageManager(production_dir=prod, staging_dir=stag, quarantine_dir=quar)

    t1 = datetime(2024, 1, 2, tzinfo=UTC)
    t2 = datetime(2024, 1, 3, tzinfo=UTC)
    pm.write_bars_atomic([make_bar(ts=t1, close=100.0)], Timeframe.D1)

    # Overwrite t1 and add t2
    pm.write_bars_atomic(
        [
            make_bar(ts=t1, open_=108.0, high=112.0, low=105.0, close=110.0),
            make_bar(ts=t2, open_=108.0, high=115.0, low=105.0, close=112.0),
        ],
        Timeframe.D1,
        overwrite_existing=True,
    )

    df = pm.read_bars("600519.SH", Timeframe.D1, t1, t2)
    assert len(df) == 2
    assert df.filter(pl.col("ts") == t1)["close"][0] == 110.0


def test_parquet_quarantine_routing(temp_dirs: tuple[Path, Path, Path, Path]) -> None:
    prod, stag, quar, _ = temp_dirs
    pm = ParquetStorageManager(production_dir=prod, staging_dir=stag, quarantine_dir=quar)

    dirty_bars = [make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC))]
    report = DataQualityReport(
        symbol="600519.SH",
        timeframe=Timeframe.D1,
        source_id="test",
        status=DataQualityStatus.REJECT,
        total_rows=1,
    )
    quar_path = pm.route_to_quarantine(dirty_bars, report)
    assert quar_path.exists()
    assert quar_path.suffix == ".parquet"


@pytest.mark.asyncio
async def test_sqlite_metadata_lifecycle(temp_dirs: tuple[Path, Path, Path, Path]) -> None:
    prod, _, _, _ = temp_dirs
    db_path = prod.parent / "test_meta.db"
    meta = SQLiteMetadataManager(db_path=db_path)
    await meta.connect()

    # Check WAL mode
    async with meta.conn.execute("PRAGMA journal_mode;") as cur:
        row = await cur.fetchone()
        assert row is not None and row[0].lower() == "wal"

    # Upsert Security
    sec = Security(
        symbol="600519.SH",
        name="贵州茅台",
        market=Market.CN_A,
        asset_type=AssetType.STOCK,
        listing_status=ListingStatus.LISTED,
        currency="CNY",
    )
    assert await meta.upsert_securities([sec]) == 1
    fetched = await meta.get_security("600519.SH")
    assert fetched is not None
    assert fetched.name == "贵州茅台"

    # Adjustment Events
    ev = AdjustmentEvent(
        symbol="600519.SH",
        ex_date=datetime(2024, 6, 15, tzinfo=UTC),
        cash_dividend=1.05,
        bonus_ratio=0.0,
        rights_ratio=0.0,
        rights_price=0.0,
        source_id="akshare",
    )
    assert await meta.upsert_adjustment_events([ev]) == 1
    events = await meta.get_adjustment_events(
        "600519.SH",
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 12, 31, tzinfo=UTC),
    )
    assert len(events) == 1
    assert events[0].cash_dividend == 1.05

    # Coverage
    start_d = datetime(2024, 1, 2, tzinfo=UTC)
    end_d = datetime(2024, 1, 3, tzinfo=UTC)
    await meta.update_coverage(
        symbol="600519.SH",
        timeframe=Timeframe.D1,
        start_date=start_d,
        end_date=end_d,
        row_count=2,
        file_path=prod / "CN_A" / "1d" / "600519.SH.parquet",
        file_hash="dummyhash",
        quality_status="PASS",
    )
    cov_start, cov_end = await meta.get_coverage("600519.SH", Timeframe.D1)
    assert cov_start == start_d
    assert cov_end == end_d

    await meta.close()


@pytest.mark.asyncio
async def test_duckdb_engine(temp_dirs: tuple[Path, Path, Path, Path]) -> None:
    prod, _, _, _ = temp_dirs
    engine = DuckDBEngine(production_dir=prod)
    engine.connect()

    df = await engine.query("SELECT 100 AS num, 'test' AS text")
    assert len(df) == 1
    assert df["num"][0] == 100

    df_param = await engine.query("SELECT ? AS val", {"val": 42})
    assert len(df_param) == 1
    assert df_param["val"][0] == 42

    engine.close()


@pytest.mark.asyncio
async def test_composite_storage_engine_full(temp_dirs: tuple[Path, Path, Path, Path]) -> None:
    prod, stag, quar, raw = temp_dirs
    root = prod.parent
    storage = CompositeStorageEngine(data_root=root, meta_db_path=root / "meta.db")
    await storage.initialise()

    bars = [
        make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC), close=100.0),
        make_bar(ts=datetime(2024, 1, 3, tzinfo=UTC), close=105.0),
    ]

    written = await storage.write_bars(bars)
    assert written == 2

    # Verify coverage in SQLite
    c_start, c_end = await storage.get_coverage("600519.SH", Timeframe.D1)
    assert c_start == datetime(2024, 1, 2, tzinfo=UTC)
    assert c_end == datetime(2024, 1, 3, tzinfo=UTC)

    # Verify read
    df = await storage.read_bars(
        "600519.SH",
        Timeframe.D1,
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert len(df) == 2
    assert df["close"].to_list() == [100.0, 105.0]

    # Verify integrity
    assert await storage.verify_integrity("600519.SH", Timeframe.D1) is True

    await storage.close()
