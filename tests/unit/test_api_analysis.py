"""
tests/unit/test_api_analysis.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the FastAPI analytics endpoints (/api/v1/analysis/*).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.v1.analysis as analysis_module
import api.v1.market as market_module
from api.app import app
from core.entities import (
    AdjustType,
    AssetType,
    ListingStatus,
    Market,
    MarketBar,
    Security,
    Timeframe,
)
from storage.composite_engine import CompositeStorageEngine

client = TestClient(app)


@pytest.fixture
def mock_storage(tmp_path: Path) -> Generator[CompositeStorageEngine, None, None]:
    engine = CompositeStorageEngine(
        data_root=tmp_path / "data",
        meta_db_path=tmp_path / "meta.db",
    )
    import asyncio

    asyncio.run(engine.initialise())

    orig_engine = market_module._storage_engine
    market_module._storage_engine = engine

    # Seed securities & bars for 600519.SH and benchmark 000001.SH
    sec1 = Security(
        symbol="600519.SH",
        name="贵州茅台",
        market=Market.CN_A,
        asset_type=AssetType.STOCK,
        listing_status=ListingStatus.LISTED,
        currency="CNY",
    )
    sec_bench = Security(
        symbol="000001.SH",
        name="上证指数",
        market=Market.INDEX,
        asset_type=AssetType.INDEX,
        listing_status=ListingStatus.LISTED,
        currency="CNY",
    )
    asyncio.run(engine.sqlite.upsert_securities([sec1, sec_bench]))

    # Seed 50 bars
    base_dt = datetime(2023, 1, 1, tzinfo=UTC)
    s_bars = []
    b_bars = []
    for i in range(50):
        dt = base_dt + timedelta(days=i)
        p_stock = 100.0 + i * 0.5
        p_bench = 3000.0 + i * 2.0
        s_bars.append(
            MarketBar(
                symbol="600519.SH",
                timeframe=Timeframe.D1,
                adj_type=AdjustType.NONE,
                ts=dt,
                open=p_stock - 0.2,
                high=p_stock + 0.5,
                low=p_stock - 0.5,
                close=p_stock,
                volume=1000.0,
                amount=p_stock * 1000.0,
                source_id="test",
            )
        )
        b_bars.append(
            MarketBar(
                symbol="000001.SH",
                timeframe=Timeframe.D1,
                adj_type=AdjustType.NONE,
                ts=dt,
                open=p_bench - 2.0,
                high=p_bench + 5.0,
                low=p_bench - 5.0,
                close=p_bench,
                volume=50000.0,
                amount=p_bench * 50000.0,
                source_id="test",
            )
        )

    asyncio.run(engine.write_bars(s_bars))
    asyncio.run(engine.write_bars(b_bars))

    analysis_module._analytics_cache.invalidate_all()

    yield engine

    asyncio.run(engine.close())
    market_module._storage_engine = orig_engine
    analysis_module._analytics_cache.invalidate_all()


def test_api_indicators(mock_storage: CompositeStorageEngine) -> None:
    resp = client.get(
        "/api/v1/analysis/indicators?symbol=600519.SH&timeframe=1d&adj_type=none&limit=50"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600519.SH"
    assert data["count"] == 50
    assert len(data["rows"]) == 50

    latest_row = data["rows"][-1]
    assert "ma_5" in latest_row
    assert "ma_20" in latest_row
    assert "macd_dif" in latest_row
    assert "rsi_14" in latest_row
    assert "kdj_k" in latest_row
    assert "boll_mid" in latest_row
    assert "atr_14" in latest_row
    assert latest_row["ma_5"] is not None


def test_api_market_breadth(mock_storage: CompositeStorageEngine) -> None:
    resp = client.get("/api/v1/analysis/breadth?market=CN_A")
    assert resp.status_code == 200
    data = resp.json()
    assert data["market"] == "CN_A"
    assert "advance_count" in data
    assert "decline_count" in data
    assert "distribution" in data
    assert "survivorship_bias_warning" in data


def test_api_sectors(mock_storage: CompositeStorageEngine) -> None:
    resp = client.get("/api/v1/analysis/sectors?benchmark_symbol=000001.SH")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sectors"] > 0
    assert len(data["sectors"]) > 0
    first_sector = data["sectors"][0]
    assert "sector_name" in first_sector
    assert "avg_change_pct" in first_sector
    assert "relative_strength_vs_bench" in first_sector


def test_api_relative_performance(mock_storage: CompositeStorageEngine) -> None:
    resp = client.get(
        "/api/v1/analysis/relative-performance?symbol=600519.SH&benchmark_symbol=000001.SH&limit=50"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600519.SH"
    assert data["benchmark_symbol"] == "000001.SH"
    assert data["sample_count"] > 10
    assert "beta" in data
    assert "alpha_annualized" in data
    assert "correlation" in data
    assert "r_squared" in data
