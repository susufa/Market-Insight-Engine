"""
tests/unit/test_step6_provenance_and_revision.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Step6 Unit tests verifying:
1. Raw response archival and cryptographic hashing.
2. Historical data revision detection and SQLite audit persistence.
3. Storage post-write callback and API cache invalidation.
4. API response provenance transparency.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from adapters.akshare_adapter import AKShareAdapter
from api.app import create_app
from api.v1.market import (
    _bars_cache,
    invalidate_bars_cache,
)
from core.entities import (
    AdjustType,
    DataOrigin,
    MarketBar,
    Timeframe,
)
from storage.composite_engine import CompositeStorageEngine
from storage.sqlite_meta import SQLiteMetadataManager


@pytest.fixture
def temp_dirs(tmp_path: Path):
    prod = tmp_path / "production"
    stag = tmp_path / "staging"
    quar = tmp_path / "quarantine"
    raw = tmp_path / "raw"
    db_path = tmp_path / "meta.db"
    for d in (prod, stag, quar, raw):
        d.mkdir(parents=True, exist_ok=True)
    return {
        "production": prod,
        "staging": stag,
        "quarantine": quar,
        "raw": raw,
        "db_path": db_path,
        "root": tmp_path,
    }


# =========================================================================== #
# 1. Raw Response Provenance Tests
# =========================================================================== #


@pytest.mark.asyncio
async def test_raw_response_archival_and_sqlite(temp_dirs):
    """Verify raw response is hashed, dumped to disk (if configured), and saved in SQLite."""
    db_path = temp_dirs["db_path"]
    sqlite = SQLiteMetadataManager(db_path=db_path)
    await sqlite.connect()

    raw_dir = temp_dirs["raw"]
    adapter = AKShareAdapter(max_retries=1, raw_storage_dir=raw_dir)

    # Mock EastMoney response
    mock_df = pd.DataFrame(
        [
            {
                "日期": "2026-01-05",
                "开盘": 100.0,
                "收盘": 105.0,
                "最高": 108.0,
                "最低": 99.0,
                "成交量": 100000.0,
                "成交额": 10300000.0,
            },
            {
                "日期": "2026-01-06",
                "开盘": 105.0,
                "收盘": 102.0,
                "最高": 107.0,
                "最低": 101.0,
                "成交量": 90000.0,
                "成交额": 9200000.0,
            },
        ]
    )

    with patch("akshare.stock_zh_a_hist", return_value=mock_df):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 10, tzinfo=UTC)
        bars, archive = await adapter.fetch_bars_with_archive("600519.SH", Timeframe.D1, start, end)

    assert len(bars) == 2
    assert archive is not None
    assert archive.symbol == "600519.SH"
    assert archive.row_count == 2
    assert archive.response_status == "SUCCESS"
    assert archive.source_interface == "akshare:stock_zh_a_hist"
    assert len(archive.raw_response_hash) == 64
    assert len(archive.normalized_data_hash) == 64
    assert Path(archive.raw_payload_path).exists()

    # Save to SQLite and query back
    await sqlite.insert_raw_response_archive(archive)
    records = await sqlite.get_raw_response_archives("600519.SH")
    assert len(records) == 1
    rec = records[0]
    assert rec.raw_response_hash == archive.raw_response_hash
    assert rec.normalized_data_hash == archive.normalized_data_hash
    assert rec.row_count == 2

    await sqlite.close()


# =========================================================================== #
# 2. Historical Data Revision Detection Tests
# =========================================================================== #


@pytest.mark.asyncio
async def test_historical_revision_detection(temp_dirs):
    """Verify overwriting historical bars with modified prices triggers DataRevisionRecord."""
    engine = CompositeStorageEngine(data_root=temp_dirs["root"], meta_db_path=temp_dirs["db_path"])
    await engine.initialise()

    ts1 = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    ts2 = datetime(2026, 1, 6, 0, 0, tzinfo=UTC)

    # Initial batch
    bars_initial = [
        MarketBar(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=ts1,
            open=100.0,
            high=105.0,
            low=99.0,
            close=102.0,
            volume=50000.0,
            amount=5100000.0,
            source_id="akshare",
            checksum="chk1",
        ),
        MarketBar(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=ts2,
            open=102.0,
            high=108.0,
            low=101.0,
            close=106.0,
            volume=60000.0,
            amount=6300000.0,
            source_id="akshare",
            checksum="chk2",
        ),
    ]

    await engine.write_bars(bars_initial)
    revisions_init = await engine.get_data_revisions("600519.SH")
    assert len(revisions_init) == 0

    # Revised batch (retrospective corporate adjustment: ts1 close revised from 102 to 98)
    bars_revised = [
        MarketBar(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=ts1,
            open=100.0,
            high=105.0,
            low=97.0,
            close=98.0,  # MODIFIED
            volume=50000.0,
            amount=4900000.0,
            source_id="akshare",
            checksum="chk1_rev",
        ),
        MarketBar(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=ts2,
            open=102.0,
            high=108.0,
            low=101.0,
            close=106.0,  # Unchanged
            volume=60000.0,
            amount=6300000.0,
            source_id="akshare",
            checksum="chk2",
        ),
    ]

    # Write with overwrite_existing=True
    await engine.write_bars(bars_revised, overwrite_existing=True)

    revisions = await engine.get_data_revisions("600519.SH")
    assert len(revisions) == 1
    rev = revisions[0]
    assert rev.symbol == "600519.SH"
    assert rev.revised_ts_count == 1
    assert rev.old_fingerprint != rev.new_fingerprint
    assert len(rev.sample_diffs) == 1
    assert "old_close" in rev.sample_diffs[0]

    await engine.close()


# =========================================================================== #
# 3. Post-Write Callback & Cache Invalidation
# =========================================================================== #


@pytest.mark.asyncio
async def test_cache_invalidation_on_write(temp_dirs):
    """Verify write_bars triggers post-write callback and clears API cache."""
    engine = CompositeStorageEngine(data_root=temp_dirs["root"], meta_db_path=temp_dirs["db_path"])
    await engine.initialise()

    callback_called = []

    def on_write(symbol: str, tf: Timeframe):
        callback_called.append((symbol, tf))
        invalidate_bars_cache(symbol)

    engine.register_post_write_callback(on_write)

    # Seed API cache manually
    _bars_cache[("600519.SH", "1d", "none", "", "", 100)] = {"dummy": True}
    assert ("600519.SH", "1d", "none", "", "", 100) in _bars_cache

    bar = MarketBar(
        symbol="600519.SH",
        timeframe=Timeframe.D1,
        adj_type=AdjustType.NONE,
        ts=datetime(2026, 1, 10, tzinfo=UTC),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10000.0,
        amount=1005000.0,
        source_id="test",
    )
    await engine.write_bars([bar])

    assert len(callback_called) == 1
    assert callback_called[0] == ("600519.SH", Timeframe.D1)
    # Check that cache was invalidated
    assert ("600519.SH", "1d", "none", "", "", 100) not in _bars_cache

    await engine.close()


# =========================================================================== #
# 4. API Provenance Fields Test
# =========================================================================== #


@pytest.mark.asyncio
async def test_api_bars_and_quote_provenance(temp_dirs):
    """Verify GET /bars and GET /quote expose data_origin and source_interface."""
    engine = CompositeStorageEngine(data_root=temp_dirs["root"], meta_db_path=temp_dirs["db_path"])
    await engine.initialise()

    ts = datetime(2026, 1, 15, tzinfo=UTC)
    bar = MarketBar(
        symbol="000858.SZ",
        timeframe=Timeframe.D1,
        adj_type=AdjustType.NONE,
        ts=ts,
        open=150.0,
        high=155.0,
        low=149.0,
        close=153.0,
        volume=20000.0,
        amount=3060000.0,
        source_id="akshare",
        data_origin=DataOrigin.REAL_PROVIDER,
        source_interface="akshare:stock_zh_a_daily",
        checksum="testchk123",
    )
    await engine.write_bars([bar])

    with patch("api.v1.market.get_storage", return_value=engine):
        client = TestClient(create_app())

        resp = client.get("/api/v1/market/bars?symbol=000858.SZ&timeframe=1d")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["data_origin"] == "real_provider"
        assert data["source_interface"] == "akshare:stock_zh_a_daily"
        assert len(data["data_fingerprint"]) > 0

        q_resp = client.get("/api/v1/market/quote?symbol=000858.SZ")
        assert q_resp.status_code == 200
        q_data = q_resp.json()
        assert q_data["symbol"] == "000858.SZ"
        assert q_data["last_price"] == 153.0
        assert q_data["data_origin"] == "real_provider"
        assert q_data["source_interface"] == "akshare:stock_zh_a_daily"

    await engine.close()
