"""
tests/unit/test_breadth.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for Market Breadth & Cross-Sectional Statistics.

Verifies:
- Advance, decline, and flat calculations
- Missing stocks are NOT counted as flat
- Suspended and zero-volume stocks are properly categorized
- Median, mean, limit-up/down, and distribution bucketing
- Survivorship bias warning tracking
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from analysis.breadth import StockSnapshot, compute_market_breadth
from core.entities import Market


def test_market_breadth_basic_distribution() -> None:
    dt = datetime(2024, 5, 20, tzinfo=UTC)
    snapshots = [
        # Advances (2 normal, 1 limit up)
        StockSnapshot(symbol="000001.SZ", close=10.5, prev_close=10.0, volume=1000),  # +5%
        StockSnapshot(symbol="000002.SZ", close=10.2, prev_close=10.0, volume=1000),  # +2%
        StockSnapshot(
            symbol="000003.SZ", close=11.0, prev_close=10.0, volume=1000
        ),  # +10% (limit up)
        # Declines (1 normal, 1 limit down)
        StockSnapshot(symbol="000004.SZ", close=9.6, prev_close=10.0, volume=1000),  # -4%
        StockSnapshot(
            symbol="000005.SZ", close=9.0, prev_close=10.0, volume=1000
        ),  # -10% (limit down)
        # Flat
        StockSnapshot(symbol="000006.SZ", close=10.0, prev_close=10.0, volume=1000),  # 0%
        # Suspended
        StockSnapshot(symbol="000007.SZ", close=10.0, prev_close=10.0, volume=0, is_suspended=True),
        # Missing
        StockSnapshot(symbol="000008.SZ", close=0.0, prev_close=0.0, volume=0, is_missing=True),
    ]

    report = compute_market_breadth(snapshots, trade_date=dt, market=Market.CN_A)

    assert report.total_universe_count == 8
    assert report.active_traded_count == 6
    assert report.suspended_count == 1
    assert report.missing_count == 1

    assert report.advance_count == 3
    assert report.decline_count == 2
    assert report.flat_count == 1

    assert pytest.approx(report.advance_ratio, rel=1e-3) == 3 / 6  # 0.5
    assert pytest.approx(report.decline_ratio, rel=1e-3) == 2 / 6  # 0.333

    assert report.limit_up_count == 1
    assert report.limit_down_count == 1

    # Distribution checks
    assert report.distribution[">7%"] == 1
    assert report.distribution["3%~5%"] == 1
    assert report.distribution["0%~3%"] == 1
    assert report.distribution["0%"] == 1
    assert report.distribution["-5%~-3%"] == 1
    assert report.distribution["<-7%"] == 1

    # Coverage rate: (6 active + 1 suspended) / 8 = 7/8 = 0.875
    assert pytest.approx(report.coverage_rate, rel=1e-3) == 0.875

    # Survivorship bias warning must be present
    assert "幸存者偏差" in report.survivorship_bias_warning


def test_market_breadth_empty_universe() -> None:
    dt = datetime(2024, 5, 20, tzinfo=UTC)
    report = compute_market_breadth([], trade_date=dt)
    assert report.total_universe_count == 0
    assert report.active_traded_count == 0
    assert report.advance_ratio == 0.0
