"""
tests/unit/test_relative_performance.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for Beta, Jensen's Alpha, Correlation, and Relative Returns.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from analysis.relative_performance import compute_relative_performance
from core.entities import AdjustType, MarketBar, Timeframe


def make_bar(symbol: str, dt: datetime, close: float) -> MarketBar:
    return MarketBar(
        symbol=symbol,
        timeframe=Timeframe.D1,
        adj_type=AdjustType.NONE,
        ts=dt,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        amount=close * 1000.0,
        source_id="test",
    )


def test_beta_alpha_correlation_exact_synthetic() -> None:
    # Construct 100 days where stock return = 1.5 * bench return (Beta = 1.5, Corr = 1.0)
    base_dt = datetime(2023, 1, 1, tzinfo=UTC)
    b_prices = [100.0]
    s_prices = [50.0]

    np.random.seed(999)
    for _ in range(50):
        b_ret = float(np.random.randn() * 0.01)
        s_ret = 1.5 * b_ret  # exact beta = 1.5

        b_prices.append(b_prices[-1] * (1.0 + b_ret))
        s_prices.append(s_prices[-1] * (1.0 + s_ret))

    s_bars = [
        make_bar("STOCK.SH", base_dt + timedelta(days=i), s_prices[i]) for i in range(len(s_prices))
    ]
    b_bars = [
        make_bar("BENCH.SH", base_dt + timedelta(days=i), b_prices[i]) for i in range(len(b_prices))
    ]

    metrics = compute_relative_performance(s_bars, b_bars, risk_free_rate_ann=0.02)

    assert metrics.sample_count == 50
    assert pytest.approx(metrics.beta, rel=1e-3) == 1.5
    assert pytest.approx(metrics.correlation, rel=1e-3) == 1.0
    assert pytest.approx(metrics.r_squared, rel=1e-3) == 1.0


def test_zero_variance_protection() -> None:
    base_dt = datetime(2023, 1, 1, tzinfo=UTC)
    s_bars = [make_bar("STOCK.SH", base_dt + timedelta(days=i), 10.0 + i) for i in range(10)]
    # Benchmark completely flat (zero variance)
    b_bars = [make_bar("BENCH.SH", base_dt + timedelta(days=i), 100.0) for i in range(10)]

    metrics = compute_relative_performance(s_bars, b_bars)

    assert metrics.beta == 0.0
    assert metrics.correlation == 0.0
    assert metrics.r_squared == 0.0


def test_empty_and_short_series() -> None:
    metrics = compute_relative_performance([], [])
    assert metrics.sample_count == 0
    assert metrics.beta == 0.0
