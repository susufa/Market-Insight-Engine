import asyncio
import os
import shutil
import tempfile
from datetime import datetime, UTC, timedelta
from pathlib import Path
import pytest
import polars as pl

from core.entities import MarketBar, Timeframe, AdjustType, DataOrigin
from storage.composite_engine import CompositeStorageEngine
from storage.parquet_manager import calculate_file_checksums

@pytest.fixture
def temp_engine_dir():
    d = tempfile.mkdtemp(prefix="mie_storage_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)

@pytest.mark.asyncio
async def test_idempotent_writes(temp_engine_dir):
    """Writing the exact same bars multiple times must produce identical row count and no duplicates."""
    engine = CompositeStorageEngine(data_root=temp_engine_dir)
    await engine.initialise()
    
    symbol = "600519.SH"
    tf = Timeframe.D1
    base_dt = datetime(2023, 1, 3, tzinfo=UTC)
    
    # 5 bars
    bars = [
        MarketBar(
            symbol=symbol,
            timeframe=tf,
            adj_type=AdjustType.NONE,
            ts=base_dt + timedelta(days=i),
            open=1800.0 + i,
            high=1850.0 + i,
            low=1790.0 + i,
            close=1830.0 + i,
            volume=10000.0,
            amount=18300000.0,
            source_id="akshare",
            data_origin=DataOrigin.REAL_PROVIDER,
            source_interface="akshare:stock_zh_a_daily",
            checksum="test_check",
            fetched_at=datetime.now(UTC),
        )
        for i in range(5)
    ]
    
    # Write 1st time
    await engine.write_bars(bars)
    start_cov, end_cov = await engine.sqlite.get_coverage(symbol, tf)
    assert start_cov == bars[0].ts
    assert end_cov == bars[-1].ts
    
    df1 = await engine.read_bars(symbol, tf, start_cov, end_cov)
    assert len(df1) == 5
    
    # Check SHA256 of parquet
    p_path = engine.parquet.get_production_path(symbol, tf)
    _, hash1 = calculate_file_checksums(p_path)
    
    # Write 2nd time (identical bars)
    await engine.write_bars(bars)
    df2 = await engine.read_bars(symbol, tf, start_cov, end_cov)
    assert len(df2) == 5, f"Expected 5 rows, got {len(df2)} (duplication occurred!)"
    
    # SQLite coverage row count must still be 5
    async with engine.sqlite.conn.execute(
        "SELECT row_count, file_hash FROM bar_coverage WHERE symbol = ? AND timeframe = ?",
        (symbol, tf.value)
    ) as cur:
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == 5
        assert row[1] == hash1
        
    await engine.close()

@pytest.mark.asyncio
async def test_incremental_updates(temp_engine_dir):
    """Appending subsequent dates must smoothly merge into existing parquet without gaps or loss."""
    engine = CompositeStorageEngine(data_root=temp_engine_dir)
    await engine.initialise()
    
    symbol = "000001.SZ"
    tf = Timeframe.D1
    base_dt = datetime(2023, 1, 3, tzinfo=UTC)
    
    # Batch 1: days 0, 1, 2
    batch1 = [
        MarketBar(
            symbol=symbol,
            timeframe=tf,
            adj_type=AdjustType.NONE,
            ts=base_dt + timedelta(days=i),
            open=10.0 + i,
            high=11.0 + i,
            low=9.5 + i,
            close=10.5 + i,
            volume=50000.0,
            amount=525000.0,
            source_id="akshare",
            data_origin=DataOrigin.REAL_PROVIDER,
            source_interface="akshare:stock_zh_a_daily",
            checksum="chk1",
            fetched_at=datetime.now(UTC),
        )
        for i in range(3)
    ]
    await engine.write_bars(batch1)
    
    # Check coverage
    s1, e1 = await engine.sqlite.get_coverage(symbol, tf)
    assert e1 == batch1[-1].ts
    
    # Batch 2: day 2 (overlapping) and days 3, 4 (incremental)
    batch2 = [
        MarketBar(
            symbol=symbol,
            timeframe=tf,
            adj_type=AdjustType.NONE,
            ts=base_dt + timedelta(days=i),
            open=10.0 + i,
            high=11.0 + i,
            low=9.5 + i,
            close=10.5 + i,
            volume=50000.0,
            amount=525000.0,
            source_id="akshare",
            data_origin=DataOrigin.REAL_PROVIDER,
            source_interface="akshare:stock_zh_a_daily",
            checksum="chk2",
            fetched_at=datetime.now(UTC),
        )
        for i in range(2, 5)
    ]
    await engine.write_bars(batch2)
    
    # Total distinct days: 0, 1, 2, 3, 4 -> 5 bars
    s2, e2 = await engine.sqlite.get_coverage(symbol, tf)
    assert s2 == batch1[0].ts
    assert e2 == batch2[-1].ts
    
    df_all = await engine.read_bars(symbol, tf, s2, e2)
    assert len(df_all) == 5
    assert df_all["ts"].to_list() == sorted(df_all["ts"].to_list())
    
    await engine.close()
