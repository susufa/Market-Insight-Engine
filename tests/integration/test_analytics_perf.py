"""
tests/integration/test_analytics_perf.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Performance benchmarks for Phase 4:
- Single stock 1500 bars all indicators (target < 50ms)
- Cross-sectional 3000 symbols market breadth (target < 1000ms)
- Batch multi-stock technical indicators computation
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import numpy as np

from analysis.breadth import StockSnapshot, compute_market_breadth
from analysis.indicators.engine import IndicatorEngine
from core.entities import AdjustType, MarketBar, Timeframe


def generate_benchmark_bars(symbol: str, count: int) -> list[MarketBar]:
    base_dt = datetime(2018, 1, 2, tzinfo=UTC)
    np.random.seed(42)
    prices = 100.0 + np.cumsum(np.random.randn(count) * 0.5)
    return [
        MarketBar(
            symbol=symbol,
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=base_dt + timedelta(days=i),
            open=float(prices[i] - 0.2),
            high=float(prices[i] + 0.6),
            low=float(prices[i] - 0.6),
            close=float(prices[i]),
            volume=10000.0,
            amount=prices[i] * 10000.0,
            source_id="perf",
        )
        for i in range(count)
    ]


def test_perf_single_stock_1500_bars_all_indicators() -> None:
    """
    Requirement 6.2:
    1500 bars full indicators computation must complete in < 50ms.
    """
    engine = IndicatorEngine()
    bars = generate_benchmark_bars("600519.SH", 1500)

    # Warm-up run
    _ = engine.compute_all(bars)

    # Timed runs (10 iterations)
    durations_ms = []
    for _ in range(10):
        t0 = time.perf_counter()
        df = engine.compute_all(bars)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        durations_ms.append(elapsed_ms)
        assert len(df) == 1500

    avg_ms = sum(durations_ms) / len(durations_ms)
    min_ms = min(durations_ms)

    print(f"\n[Perf Benchmark] 1500 bars all indicators: Avg={avg_ms:.2f}ms, Min={min_ms:.2f}ms")
    assert avg_ms < 50.0, f"Average compute time {avg_ms:.2f}ms exceeded 50ms threshold"


def test_perf_3000_symbols_market_breadth() -> None:
    """
    Requirement 6.2:
    3000 symbols cross-sectional breadth calculation must complete in < 1000ms.
    """
    dt = datetime(2024, 5, 20, tzinfo=UTC)
    np.random.seed(1234)

    # Synthesize 3000 cross-sectional stock quotes
    snapshots: list[StockSnapshot] = []
    for i in range(3000):
        p_prev = 10.0 + (i % 100)
        ret = float(np.random.randn() * 0.03)
        p_close = p_prev * (1.0 + ret)
        is_susp = i % 20 == 0  # 5% suspended
        is_miss = i % 50 == 0  # 2% missing
        vol = 0.0 if (is_susp or is_miss) else 10000.0

        snapshots.append(
            StockSnapshot(
                symbol=f"{i:06d}.SZ",
                close=p_close,
                prev_close=p_prev,
                volume=vol,
                is_suspended=is_susp,
                is_missing=is_miss,
            )
        )

    t0 = time.perf_counter()
    report = compute_market_breadth(snapshots, trade_date=dt)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n[Perf Benchmark] 3000 symbols market breadth: Elapsed={elapsed_ms:.2f}ms")
    assert report.total_universe_count == 3000
    assert elapsed_ms < 1000.0, f"Breadth calculation took {elapsed_ms:.2f}ms > 1000ms"
