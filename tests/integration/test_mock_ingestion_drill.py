"""
tests/integration/test_mock_ingestion_drill.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Simulated full-scale ingestion drill (100 securities, multi-year daily bars)
using synthetic offline data to demonstrate full pipeline throughput,
atomic write performance, SQLite metadata tracking, and DuckDB analytical query.
"""

from __future__ import annotations

import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.entities import (
    AdjustType,
    DataQualityStatus,
    MarketBar,
    Timeframe,
)
from quality.validator import QualityValidator
from storage.composite_engine import CompositeStorageEngine


def generate_mock_bars(symbol: str, target_trading_bars: int = 1460) -> list[MarketBar]:
    """
    Generate exact `target_trading_bars` daily bars (excluding weekends)
    representing ~6 years of continuous trading sessions (~243 trading days/year).
    """
    bars: list[MarketBar] = []
    base_ts = datetime(2018, 1, 2, tzinfo=UTC)
    price = 100.0
    day_offset = 0

    while len(bars) < target_trading_bars:
        cur_ts = base_ts + timedelta(days=day_offset)
        day_offset += 1
        if cur_ts.weekday() >= 5:
            continue
        open_p = round(price, 2)
        high_p = round(price * 1.02, 2)
        low_p = round(price * 0.98, 2)
        close_p = round(price * 1.01, 2)
        vol = 10000.0
        amt = vol * close_p

        bars.append(
            MarketBar(
                symbol=symbol,
                timeframe=Timeframe.D1,
                adj_type=AdjustType.NONE,
                ts=cur_ts,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=vol,
                amount=amt,
                source_id="mock_adapter",
            )
        )
        price = close_p
    return bars


@pytest.mark.asyncio
async def test_full_pipeline_100_symbols_drill() -> None:
    """
    End-to-end integration test verifying that the pipeline can ingest,
    validate, atomically commit, index, and query 100 securities with 6 years
    of daily data in an offline deterministic environment.
    """
    tmp = Path(tempfile.mkdtemp())
    engine = CompositeStorageEngine(data_root=tmp, meta_db_path=tmp / "meta.db")
    await engine.initialise()
    validator = QualityValidator()

    # 100 benchmark symbols
    symbols = [f"60{i:04d}.SH" for i in range(50)] + [f"00{i:04d}.SZ" for i in range(50)]
    assert len(symbols) == 100

    total_bars = 0
    start_time = time.time()

    for sym in symbols:
        # Generate exact 1460 trading days (~6 years)
        bars = generate_mock_bars(sym, target_trading_bars=1460)
        report = validator.validate(bars, Timeframe.D1)
        assert report.status == DataQualityStatus.PASS

        written = await engine.write_bars(bars)
        assert written == len(bars)
        total_bars += written

    elapsed = time.time() - start_time
    assert total_bars == 100 * 1460  # Exactly 146,000 bars

    # Verify coverage across all 100 symbols
    for sym in symbols:
        c_start, c_end = await engine.get_coverage(sym, Timeframe.D1)
        assert c_start is not None
        assert c_end is not None
        assert await engine.verify_integrity(sym, Timeframe.D1) is True

    # Verify DuckDB OLAP query across all written files
    query_sql = f"SELECT count(*) as total_rows FROM read_parquet('{tmp}/production/**/*.parquet')"
    df = await engine.query(query_sql)
    assert df["total_rows"][0] == total_bars

    await engine.close()

    # Assert reasonable processing speed (e.g. > 5000 bars/second)
    assert total_bars > 100000
    assert elapsed < 30.0
