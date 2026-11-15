"""
tests/unit/test_analytics_cache.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for Analytics Cache & Incremental Computation.

Verifies:
- Cache hit / miss behavior
- Cache invalidation by symbol
- Incremental computation equivalence to full recomputation
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from analysis.cache import AnalyticsCacheManager
from core.entities import AdjustType, MarketBar, Timeframe


def make_bars(symbol: str, count: int) -> list[MarketBar]:
    base_dt = datetime(2023, 1, 1, tzinfo=UTC)
    np.random.seed(42)
    prices = 100.0 + np.cumsum(np.random.randn(count) * 0.5)
    return [
        MarketBar(
            symbol=symbol,
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=base_dt + timedelta(days=i),
            open=float(prices[i] - 0.2),
            high=float(prices[i] + 0.5),
            low=float(prices[i] - 0.5),
            close=float(prices[i]),
            volume=5000.0,
            amount=prices[i] * 5000.0,
            source_id="test",
        )
        for i in range(count)
    ]


def test_cache_hit_and_invalidation() -> None:
    cache = AnalyticsCacheManager(maxsize=10, ttl=60)
    bars = make_bars("600519.SH", 80)

    # First call: miss
    df1, is_hit1 = cache.get_or_compute("600519.SH", Timeframe.D1, AdjustType.NONE, bars)
    assert not is_hit1
    assert len(df1) == 80

    # Second call: hit
    df2, is_hit2 = cache.get_or_compute("600519.SH", Timeframe.D1, AdjustType.NONE, bars)
    assert is_hit2
    assert len(df2) == 80

    # Invalidate
    del_count = cache.invalidate("600519.SH")
    assert del_count == 1

    # After invalidation: miss
    df3, is_hit3 = cache.get_or_compute("600519.SH", Timeframe.D1, AdjustType.NONE, bars)
    assert not is_hit3


def test_incremental_computation_equivalence() -> None:
    """
    CRITICAL REQUIREMENT (Task 4.5 & Gate 4):
    Verify that incremental computation produces results identical
    to full recomputation within numerical tolerance.
    """
    cache = AnalyticsCacheManager()
    total_bars = make_bars("000858.SZ", 120)

    # Initial batch: 100 bars
    initial_bars = total_bars[:100]
    df_initial, _ = cache.get_or_compute("000858.SZ", Timeframe.D1, AdjustType.NONE, initial_bars)
    assert len(df_initial) == 100

    # 20 new bars appended (total 120 bars)
    df_incremental, is_hit = cache.get_or_compute(
        "000858.SZ", Timeframe.D1, AdjustType.NONE, total_bars
    )
    assert not is_hit
    assert len(df_incremental) == 120

    # Independent full recomputation
    cache_fresh = AnalyticsCacheManager()
    df_full, _ = cache_fresh.get_or_compute("000858.SZ", Timeframe.D1, AdjustType.NONE, total_bars)
    assert len(df_full) == 120

    # Compare columns across both DataFrames for the newly appended rows (100..119)
    for col in ["ma_5", "ma_20", "macd_dif", "macd_dea", "boll_upper", "kdj_k"]:
        inc_vals = df_incremental[col][100:].to_list()
        full_vals = df_full[col][100:].to_list()
        for v_inc, v_full in zip(inc_vals, full_vals, strict=False):
            if v_inc is not None and v_full is not None:
                assert pytest.approx(v_inc, rel=1e-4) == pytest.approx(v_full, rel=1e-4)
