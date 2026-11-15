"""
tests/unit/test_api_market.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the FastAPI market data endpoints (/api/v1/market/*).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.v1.market as market_module
from api.app import app
from core.entities import (
    AdjustmentEvent,
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
    """Provide an isolated, seeded CompositeStorageEngine for API testing."""
    engine = CompositeStorageEngine(
        data_root=tmp_path / "data",
        meta_db_path=tmp_path / "meta.db",
    )
    import asyncio

    asyncio.run(engine.initialise())

    # Set as the active engine for the router
    orig_engine = market_module._storage_engine
    market_module._storage_engine = engine
    market_module._bars_cache.clear()

    yield engine

    asyncio.run(engine.close())
    market_module._storage_engine = orig_engine
    market_module._bars_cache.clear()


def test_list_securities(mock_storage: CompositeStorageEngine) -> None:
    # 1. Register test securities
    sec1 = Security(
        symbol="600519.SH",
        name="贵州茅台",
        market=Market.CN_A,
        asset_type=AssetType.STOCK,
        listing_status=ListingStatus.LISTED,
        listed_date=datetime(2001, 8, 27, tzinfo=UTC),
        currency="CNY",
    )
    sec2 = Security(
        symbol="00700.HK",
        name="腾讯控股",
        market=Market.CN_HK,
        asset_type=AssetType.STOCK,
        listing_status=ListingStatus.LISTED,
        currency="HKD",
    )
    sec3 = Security(
        symbol="000001.SH",
        name="上证指数",
        market=Market.INDEX,
        asset_type=AssetType.INDEX,
        listing_status=ListingStatus.LISTED,
        currency="CNY",
    )
    import asyncio

    asyncio.run(mock_storage.sqlite.upsert_securities([sec1, sec2, sec3]))

    # Test all
    resp = client.get("/api/v1/market/securities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3

    # Test filter by market
    resp_hk = client.get("/api/v1/market/securities?market=CN_HK")
    assert resp_hk.status_code == 200
    data_hk = resp_hk.json()
    assert data_hk["total"] == 1
    assert data_hk["items"][0]["symbol"] == "00700.HK"

    # Test search by keyword
    resp_search = client.get("/api/v1/market/securities?search=茅台")
    assert resp_search.status_code == 200
    data_search = resp_search.json()
    assert data_search["total"] == 1
    assert data_search["items"][0]["symbol"] == "600519.SH"


def test_bars_and_caching(mock_storage: CompositeStorageEngine) -> None:
    # Seed bars for 600519.SH
    bars = [
        MarketBar(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=datetime(2024, 1, 2 + i, tzinfo=UTC),
            open=100.0 + i,
            high=105.0 + i,
            low=95.0 + i,
            close=102.0 + i,
            volume=1000.0,
            amount=102000.0,
            source_id="test_src",
        )
        for i in range(5)
    ]
    import asyncio

    asyncio.run(mock_storage.write_bars(bars))

    # First query - miss
    resp = client.get("/api/v1/market/bars?symbol=600519.SH&timeframe=1d&adj_type=none")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600519.SH"
    assert data["count"] == 5
    assert data["is_cached"] is False
    assert len(data["bars"]) == 5
    assert data["bars"][0]["close"] == 102.0

    # Second query - hit
    resp2 = client.get("/api/v1/market/bars?symbol=600519.SH&timeframe=1d&adj_type=none")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_cached"] is True
    assert data2["count"] == 5


def test_bars_resampling_and_adjustment(mock_storage: CompositeStorageEngine) -> None:
    # Seed 10 consecutive trading days
    bars = [
        MarketBar(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=datetime(2024, 1, 8 + i, tzinfo=UTC),
            open=100.0,
            high=110.0,
            low=90.0,
            close=105.0,
            volume=1000.0,
            amount=105000.0,
            source_id="test_src",
        )
        for i in range(10)
    ]
    import asyncio

    asyncio.run(mock_storage.write_bars(bars))

    # Query weekly
    resp_w = client.get("/api/v1/market/bars?symbol=600519.SH&timeframe=1w&adj_type=none")
    assert resp_w.status_code == 200
    data_w = resp_w.json()
    assert data_w["timeframe"] == "1w"
    assert data_w["count"] == 2  # 10 days span across 2 calendar weeks

    # Add corporate action: cash dividend 10 CNY per share on Jan 12
    ev = AdjustmentEvent(
        symbol="600519.SH",
        ex_date=datetime(2024, 1, 12, tzinfo=UTC),
        record_date=datetime(2024, 1, 11, tzinfo=UTC),
        cash_dividend=10.0,
        source_id="test_corp",
    )
    asyncio.run(mock_storage.write_adjustment_events([ev]))

    # Query forward adjusted (qfq)
    resp_qfq = client.get("/api/v1/market/bars?symbol=600519.SH&timeframe=1d&adj_type=qfq")
    assert resp_qfq.status_code == 200
    data_qfq = resp_qfq.json()
    assert data_qfq["adj_type"] == "qfq"
    # Pre-dividend price (day 0: close=105.0) should be adjusted downward: 105 - 10 = 95.0
    assert round(data_qfq["bars"][0]["close"], 2) == 95.0


def test_bars_empty_symbol(mock_storage: CompositeStorageEngine) -> None:
    resp = client.get("/api/v1/market/bars?symbol=NON_EXISTENT.SH")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["bars"] == []
    assert data["data_quality_status"] == "NOT_FOUND"


def test_quote_endpoint(mock_storage: CompositeStorageEngine) -> None:
    bars = [
        MarketBar(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=datetime(2024, 1, 2, tzinfo=UTC),
            open=100.0,
            high=105.0,
            low=98.0,
            close=100.0,
            volume=1000.0,
            amount=100000.0,
            source_id="test_src",
        ),
        MarketBar(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=datetime(2024, 1, 3, tzinfo=UTC),
            open=101.0,
            high=108.0,
            low=99.0,
            close=105.0,
            volume=1500.0,
            amount=157500.0,
            source_id="test_src",
        ),
    ]
    import asyncio

    asyncio.run(mock_storage.write_bars(bars))

    resp = client.get("/api/v1/market/quote?symbol=600519.SH")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600519.SH"
    assert data["last_price"] == 105.0
    assert data["prev_close"] == 100.0
    assert data["change"] == 5.0
    assert data["pct_change"] == 5.0
    assert data["volume"] == 1500.0
    assert data["amount"] == 157500.0

    # 404 for unknown symbol
    resp_404 = client.get("/api/v1/market/quote?symbol=UNKNOWN.SH")
    assert resp_404.status_code == 404
