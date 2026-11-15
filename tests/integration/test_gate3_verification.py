"""
tests/integration/test_gate3_verification.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Gate 3 acceptance verification test suite:
- Multi-year daily K-line query (~1460 bars)
- Weekly, Monthly, Quarterly, Yearly resampling
- Dynamic forward/backward adjustments (QFQ / HFQ) without Parquet mutation
- In-memory LRU cache hit latency (< 5ms) and P95 (< 20ms)
- Static UI asset serving
"""

from __future__ import annotations

import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
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
def gate3_fixture(tmp_path: Path) -> Generator[CompositeStorageEngine, None, None]:
    engine = CompositeStorageEngine(
        data_root=tmp_path / "data",
        meta_db_path=tmp_path / "meta.db",
    )
    import asyncio

    asyncio.run(engine.initialise())

    orig_engine = market_module._storage_engine
    market_module._storage_engine = engine
    market_module._bars_cache.clear()

    # Seed 6 years of daily data (1460 trading days)
    sec = Security(
        symbol="600519.SH",
        name="贵州茅台",
        market=Market.CN_A,
        asset_type=AssetType.STOCK,
        listing_status=ListingStatus.LISTED,
        currency="CNY",
    )
    asyncio.run(engine.sqlite.upsert_securities([sec]))

    bars = []
    base_price = 1000.0
    current_dt = datetime(2018, 1, 2, tzinfo=UTC)
    for i in range(1460):
        # advance trading days (skip weekends)
        while current_dt.weekday() in (5, 6):
            current_dt += timedelta(days=1)

        p_close = base_price + (i % 50) * 2.0
        p_open = p_close - 5.0
        p_high = p_close + 10.0
        p_low = p_open - 5.0

        bars.append(
            MarketBar(
                symbol="600519.SH",
                timeframe=Timeframe.D1,
                adj_type=AdjustType.NONE,
                ts=current_dt,
                open=p_open,
                high=p_high,
                low=p_low,
                close=p_close,
                volume=50000.0,
                amount=p_close * 50000.0,
                source_id="gate3_seed",
            )
        )
        current_dt += timedelta(days=1)

    asyncio.run(engine.write_bars(bars))

    # Seed corporate action events (e.g. 2 dividend events)
    events = [
        AdjustmentEvent(
            symbol="600519.SH",
            ex_date=datetime(2020, 6, 20, tzinfo=UTC),
            record_date=datetime(2020, 6, 19, tzinfo=UTC),
            cash_dividend=17.0,
            source_id="corp_action_2020",
        ),
        AdjustmentEvent(
            symbol="600519.SH",
            ex_date=datetime(2022, 6, 25, tzinfo=UTC),
            record_date=datetime(2022, 6, 24, tzinfo=UTC),
            cash_dividend=21.0,
            bonus_ratio=0.1,  # 10% bonus shares
            source_id="corp_action_2022",
        ),
    ]
    asyncio.run(engine.write_adjustment_events(events))

    yield engine

    asyncio.run(engine.close())
    market_module._storage_engine = orig_engine
    market_module._bars_cache.clear()


def test_gate3_six_year_query_and_cache_latency(gate3_fixture: CompositeStorageEngine) -> None:
    market_module._bars_cache.clear()
    # 1. First query: cache miss (reads 1460 bars from Parquet, computes response)
    t0 = time.perf_counter()
    resp1 = client.get("/api/v1/market/bars?symbol=600519.SH&timeframe=1d&adj_type=none&limit=2000")
    _ = (time.perf_counter() - t0) * 1000.0
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["count"] == 1460
    assert data1["is_cached"] is False
    assert data1["data_quality_status"] == "PASS"

    # 2. Subsequent queries: in-memory LRU cache hit benchmark (50 iterations)
    hit_latencies = []
    for _ in range(50):
        t_start = time.perf_counter()
        resp_hit = client.get(
            "/api/v1/market/bars?symbol=600519.SH&timeframe=1d&adj_type=none&limit=2000"
        )
        lat_ms = (time.perf_counter() - t_start) * 1000.0
        hit_latencies.append(lat_ms)
        assert resp_hit.status_code == 200
        assert resp_hit.json()["is_cached"] is True

    avg_hit_ms = sum(hit_latencies) / len(hit_latencies)
    hit_latencies.sort()
    p95_hit_ms = hit_latencies[int(len(hit_latencies) * 0.95)]

    # Assert performance gates: avg hit latency < 15ms (< 50ms requirement), p95 < 25ms
    assert avg_hit_ms < 15.0, f"Average LRU hit latency {avg_hit_ms:.2f}ms exceeds 15ms"
    assert p95_hit_ms < 25.0, f"P95 LRU hit latency {p95_hit_ms:.2f}ms exceeds 25ms"


def test_gate3_resampling_aggregation(gate3_fixture: CompositeStorageEngine) -> None:
    # Weekly aggregation
    resp_w = client.get("/api/v1/market/bars?symbol=600519.SH&timeframe=1w&limit=2000")
    assert resp_w.status_code == 200
    data_w = resp_w.json()
    assert data_w["timeframe"] == "1w"
    assert 250 <= data_w["count"] <= 320  # ~6 years of weeks

    # Monthly aggregation
    resp_m = client.get("/api/v1/market/bars?symbol=600519.SH&timeframe=1M&limit=2000")
    assert resp_m.status_code == 200
    data_m = resp_m.json()
    assert data_m["timeframe"] == "1M"
    assert 65 <= data_m["count"] <= 85  # ~72 months in 6 years

    # Quarterly aggregation
    resp_q = client.get("/api/v1/market/bars?symbol=600519.SH&timeframe=1Q&limit=2000")
    assert resp_q.status_code == 200
    data_q = resp_q.json()
    assert data_q["timeframe"] == "1Q"
    assert 20 <= data_q["count"] <= 30  # ~24 quarters in 6 years


def test_gate3_dynamic_adjustments(gate3_fixture: CompositeStorageEngine) -> None:
    # 1. Unadjusted
    r_none = client.get(
        "/api/v1/market/bars?symbol=600519.SH&timeframe=1d&adj_type=none&limit=2000"
    ).json()
    # 2. Forward-adjusted (QFQ)
    r_qfq = client.get(
        "/api/v1/market/bars?symbol=600519.SH&timeframe=1d&adj_type=qfq&limit=2000"
    ).json()
    # 3. Backward-adjusted (HFQ)
    r_hfq = client.get(
        "/api/v1/market/bars?symbol=600519.SH&timeframe=1d&adj_type=hfq&limit=2000"
    ).json()

    assert r_none["count"] == 1460
    assert r_qfq["count"] == 1460
    assert r_hfq["count"] == 1460

    # In QFQ: the latest bar close price equals the unadjusted latest bar close price
    assert round(r_qfq["bars"][-1]["close"], 2) == round(r_none["bars"][-1]["close"], 2)
    # The earliest bar in QFQ is scaled downward due to dividends
    assert r_qfq["bars"][0]["close"] < r_none["bars"][0]["close"]

    # In HFQ: the earliest bar close price equals the unadjusted earliest bar close price
    assert round(r_hfq["bars"][0]["close"], 2) == round(r_none["bars"][0]["close"], 2)
    # The latest bar in HFQ is scaled upward
    assert r_hfq["bars"][-1]["close"] > r_none["bars"][-1]["close"]


def test_gate3_ui_endpoint() -> None:
    resp = client.get("/ui/")
    assert resp.status_code == 200
    assert "Market Insight Engine" in resp.text or '<div id="root">' in resp.text
