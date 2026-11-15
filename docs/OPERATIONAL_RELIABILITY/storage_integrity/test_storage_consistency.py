import asyncio
import os
import shutil
import tempfile
from datetime import datetime, UTC, timedelta
from pathlib import Path
import pytest
import polars as pl
import pyarrow.parquet as pq

from core.entities import MarketBar, Timeframe, AdjustType, DataOrigin
from storage.composite_engine import CompositeStorageEngine
from storage.parquet_manager import BAR_SCHEMA, calculate_file_checksums

@pytest.fixture
def temp_engine_dir():
    d = tempfile.mkdtemp(prefix="mie_storage_recovery_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)

@pytest.mark.asyncio
async def test_dangling_tmp_cleanup_and_reconciliation(temp_engine_dir):
    """Engine init must clean up dangling .tmp files and reconcile unindexed parquet files."""
    engine = CompositeStorageEngine(data_root=temp_engine_dir)
    await engine.initialise()
    
    symbol = "600519.SH"
    tf = Timeframe.D1
    base_dt = datetime(2023, 1, 3, tzinfo=UTC)
    
    bars = [
        MarketBar(
            symbol=symbol,
            timeframe=tf,
            adj_type=AdjustType.NONE,
            ts=base_dt + timedelta(days=i),
            open=1800.0,
            high=1850.0,
            low=1790.0,
            close=1830.0,
            volume=10000.0,
            amount=18300000.0,
            source_id="akshare",
            data_origin=DataOrigin.REAL_PROVIDER,
            source_interface="akshare:stock_zh_a_daily",
            checksum="chk",
            fetched_at=datetime.now(UTC),
        )
        for i in range(3)
    ]
    await engine.write_bars(bars)
    
    # Simulate a crashed process that left a .tmp file
    prod_path = engine.parquet.get_production_path(symbol, tf)
    dangling_tmp = prod_path.with_name(f".{symbol}_999999999.tmp")
    dangling_tmp.write_text("dummy incomplete payload")
    assert dangling_tmp.exists()
    
    # Simulate SQLite losing index of the file (e.g. crash before SQLite commit)
    await engine.sqlite.conn.execute("DELETE FROM bar_coverage WHERE symbol = ?", (symbol,))
    await engine.sqlite.conn.commit()
    
    # Run reconciliation
    res = await engine.sqlite.reconcile_with_disk(engine.parquet)
    assert res["cleaned_temp_files"] >= 1
    assert not dangling_tmp.exists(), "Dangling temp file must be removed!"
    assert res["reconciled_files"] >= 1
    
    # Verify SQLite recovered the index
    s, e = await engine.sqlite.get_coverage(symbol, tf)
    assert s == bars[0].ts
    assert e == bars[-1].ts
    
    await engine.close()

@pytest.mark.asyncio
async def test_production_data_schema_and_fingerprints():
    """Verify live production parquet files on disk match canonical schema and SQLite coverage."""
    prod_dir = Path("data/production")
    if not prod_dir.exists():
        pytest.skip("Production data directory does not exist")
        
    engine = CompositeStorageEngine(data_root=Path("data"))
    await engine.initialise()
    
    symbols = ["600519.SH", "000001.SZ", "000333.SZ"]
    tf = Timeframe.D1
    
    for symbol in symbols:
        p_path = engine.parquet.get_production_path(symbol, tf)
        assert p_path.exists(), f"Production parquet for {symbol} must exist"
        
        # 1. Read pyarrow metadata
        meta = pq.read_metadata(p_path)
        assert meta.num_rows > 0
        
        # 2. Check schema
        df = pl.read_parquet(p_path)
        for col_name, col_type in BAR_SCHEMA.items():
            assert col_name in df.columns, f"Column {col_name} missing from {p_path}"
            
        # 3. Check SQLite coverage
        async with engine.sqlite.conn.execute(
            "SELECT row_count, file_hash, quality_status FROM bar_coverage WHERE symbol = ? AND timeframe = ?",
            (symbol, tf.value)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None, f"Coverage record missing for {symbol}"
            row_count, file_hash, quality_status = row
            assert row_count == len(df), f"Row count mismatch in meta.db for {symbol}"
            assert quality_status == "PASS"
            
            # Check hash
            _, actual_hash = calculate_file_checksums(p_path)
            assert file_hash == actual_hash, f"File hash mismatch for {symbol}"
            
    await engine.close()
