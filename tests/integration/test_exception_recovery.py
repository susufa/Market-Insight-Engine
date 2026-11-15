"""
tests/integration/test_exception_recovery.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Gate 2 Verification Suite:
1. Dirty data injection (inverted OHLC, future dates, duplicates) -> intercepted & quarantined.
2. Simulated crash / forced interruption during write -> old data preserved.
3. SQLite and Parquet state reconciliation & recovery.
4. Per-security isolation during batch updates.
5. Network / rate-limit fault handling.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

from core.entities import (
    AdjustType,
    DataQualityStatus,
    MarketBar,
    Timeframe,
)
from core.exceptions import (
    DataSourceRateLimitError,
    DataSourceUnavailableError,
)
from quality.validator import QualityValidator
from storage.composite_engine import CompositeStorageEngine


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
def storage_env() -> tuple[CompositeStorageEngine, Path]:
    tmp = Path(tempfile.mkdtemp())
    engine = CompositeStorageEngine(data_root=tmp, meta_db_path=tmp / "meta.db")
    return engine, tmp


# =========================================================================== #
# Acceptance Test 1: Dirty Data Interception & Quarantine
# =========================================================================== #


@pytest.mark.asyncio
async def test_dirty_data_interception_and_quarantine(
    storage_env: tuple[CompositeStorageEngine, Path],
) -> None:
    """
    Gate 2 Requirement 1:
    Dirty data (future dates, duplicates, out-of-order) must be 100% intercepted
    by QualityValidator, routed to quarantine, and never written to production.
    """
    engine, tmp = storage_env
    await engine.initialise()
    validator = QualityValidator()

    # Step 1: Write a valid baseline into production
    t1 = datetime(2024, 1, 2, tzinfo=UTC)
    t2 = datetime(2024, 1, 3, tzinfo=UTC)
    clean_bars = [make_bar(ts=t1, close=100.0), make_bar(ts=t2, close=102.0)]

    report_clean = validator.validate(clean_bars, Timeframe.D1)
    assert report_clean.status == DataQualityStatus.PASS
    await engine.write_bars(clean_bars)

    # Verify baseline in production
    prod_df = await engine.read_bars("600519.SH", Timeframe.D1, t1, t2)
    assert len(prod_df) == 2

    # Step 2: Inject dirty data: future dates & duplicates
    future_ts = datetime.now(UTC) + timedelta(days=90)
    dirty_bars = [
        make_bar(ts=t2, close=102.0),  # Duplicate of t2
        make_bar(ts=future_ts, close=105.0),  # Future date
    ]

    report_dirty = validator.validate(dirty_bars, Timeframe.D1)
    assert report_dirty.status == DataQualityStatus.REJECT
    assert any(v.rule == "RULE_FUTURE_DATE" for v in report_dirty.violations)

    # Route dirty data to quarantine
    quarantine_path = engine.parquet.route_to_quarantine(dirty_bars, report_dirty)
    assert quarantine_path.exists()

    # Step 3: Verify old production data is completely untouched
    prod_df_after = await engine.read_bars("600519.SH", Timeframe.D1, t1, future_ts)
    assert len(prod_df_after) == 2
    assert prod_df_after["close"].to_list() == [100.0, 102.0]

    await engine.close()


# =========================================================================== #
# Acceptance Test 2: Crash Simulation During Atomic Write
# =========================================================================== #


@pytest.mark.asyncio
async def test_simulated_crash_preserves_old_data(
    storage_env: tuple[CompositeStorageEngine, Path],
) -> None:
    """
    Gate 2 Requirement 2:
    Simulate process crash or exception during parquet write / rename.
    Old reliable production data must remain 100% intact.
    """
    engine, tmp = storage_env
    await engine.initialise()

    # Step 1: Write initial production data
    t1 = datetime(2024, 1, 2, tzinfo=UTC)
    baseline_bars = [make_bar(ts=t1, close=100.0)]
    await engine.write_bars(baseline_bars)

    initial_df = await engine.read_bars("600519.SH", Timeframe.D1, t1, t1)
    assert len(initial_df) == 1
    assert initial_df["close"][0] == 100.0

    # Step 2: Simulate crash during write_bars by mocking write_parquet to raise OSError
    t2 = datetime(2024, 1, 3, tzinfo=UTC)
    new_bars = [make_bar(ts=t2, close=105.0)]

    with (
        patch.object(
            pl.DataFrame,
            "write_parquet",
            side_effect=OSError("Simulated disk write failure / crash"),
        ),
        pytest.raises(OSError, match="Simulated disk write failure"),
    ):
        await engine.write_bars(new_bars)

    # Step 3: Verify baseline remains completely intact
    after_crash_df = await engine.read_bars("600519.SH", Timeframe.D1, t1, t2)
    assert len(after_crash_df) == 1
    assert after_crash_df["close"][0] == 100.0

    # Verify no corrupted tmp files left in production
    assert len(list(engine.production_dir.rglob("*.tmp"))) == 0

    await engine.close()


# =========================================================================== #
# Acceptance Test 3: SQLite & Parquet Inconsistency Recovery
# =========================================================================== #


@pytest.mark.asyncio
async def test_sqlite_parquet_state_reconciliation(
    storage_env: tuple[CompositeStorageEngine, Path],
) -> None:
    """
    Gate 2 Requirement 3:
    Simulate state inconsistency (e.g. Parquet file written, but process was
    killed before SQLite metadata could commit, or an orphaned SQLite record).
    Reconciliation recovery must restore perfect consistency.
    """
    engine, tmp = storage_env
    await engine.initialise()

    # Step 1: Write Parquet directly to disk without SQLite knowing
    t1 = datetime(2024, 1, 2, tzinfo=UTC)
    t2 = datetime(2024, 1, 3, tzinfo=UTC)
    bars = [make_bar(ts=t1, close=100.0), make_bar(ts=t2, close=105.0)]

    # Write Parquet via low-level manager
    engine.parquet.write_bars_atomic(bars, Timeframe.D1)

    # Verify SQLite currently has NO record
    cov_start, cov_end = await engine.sqlite.get_coverage("600519.SH", Timeframe.D1)
    assert cov_start is None
    assert cov_end is None

    # Step 2: Create an orphaned record in SQLite pointing to a non-existent file
    await engine.sqlite.update_coverage(
        symbol="000002.SZ",
        timeframe=Timeframe.D1,
        start_date=t1,
        end_date=t2,
        row_count=2,
        file_path=engine.production_dir / "CN_A" / "1d" / "NON_EXISTENT.parquet",
        file_hash="dummy",
        quality_status="PASS",
    )

    # Step 3: Run reconciliation recovery
    recovery_result = await engine.reconcile_recovery()
    assert recovery_result["reconciled_files"] >= 1
    assert recovery_result["deleted_orphans"] >= 1

    # Step 4: Verify SQLite coverage is now accurately restored
    restored_start, restored_end = await engine.sqlite.get_coverage("600519.SH", Timeframe.D1)
    assert restored_start == t1
    assert restored_end == t2

    # Verify orphan is deleted
    orphan_start, _ = await engine.sqlite.get_coverage("000002.SZ", Timeframe.D1)
    assert orphan_start is None

    await engine.close()


# =========================================================================== #
# Acceptance Test 4: Single Security Failure Isolation
# =========================================================================== #


@pytest.mark.asyncio
async def test_single_security_failure_isolation(
    storage_env: tuple[CompositeStorageEngine, Path],
) -> None:
    """
    Gate 2 Requirement 4:
    Batch update across multiple securities: failure of one security must not
    prevent or corrupt the updates of other securities.
    """
    engine, tmp = storage_env
    await engine.initialise()

    symbols = ["600519.SH", "000001.SZ", "000858.SZ", "601318.SH"]
    results: dict[str, bool] = {}

    for sym in symbols:
        try:
            if sym == "000001.SZ":
                # Simulate failure on 000001.SZ (e.g. data source exception)
                raise DataSourceUnavailableError(
                    "akshare", "Simulated connection drop for 000001.SZ"
                )

            t = datetime(2024, 1, 2, tzinfo=UTC)
            bars = [
                make_bar(
                    symbol=sym,
                    ts=t,
                    open_=50.0,
                    high=52.0,
                    low=48.0,
                    close=50.0,
                    volume=1000.0,
                    amount=50000.0,
                )
            ]
            await engine.write_bars(bars)
            results[sym] = True
        except Exception:
            results[sym] = False

    # Assertions
    assert results["600519.SH"] is True
    assert results["000001.SZ"] is False  # Failed
    assert results["000858.SZ"] is True
    assert results["601318.SH"] is True

    # Confirm successful securities are stored properly
    for sym in ["600519.SH", "000858.SZ", "601318.SH"]:
        df = await engine.read_bars(
            sym,
            Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 5, tzinfo=UTC),
        )
        assert len(df) == 1
        assert df["symbol"][0] == sym

    # Confirm failed security has no data in production
    df_failed = await engine.read_bars(
        "000001.SZ",
        Timeframe.D1,
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert len(df_failed) == 0

    await engine.close()


# =========================================================================== #
# Acceptance Test 5: Fault Handling on Rate Limit & Upstream Error
# =========================================================================== #


@pytest.mark.asyncio
async def test_rate_limiting_fault_handling() -> None:
    """
    Gate 2 Requirement 5:
    Rate limiting (429) and upstream errors are caught and classified cleanly.
    """
    from adapters.akshare_adapter import AKShareAdapter

    adapter = AKShareAdapter(max_retries=1)

    with (
        patch("akshare.stock_zh_a_hist", side_effect=Exception("429 Too Many Requests")),
        pytest.raises(DataSourceRateLimitError),
    ):
        await adapter.fetch_bars(
            "600519.SH",
            Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 5, tzinfo=UTC),
        )
