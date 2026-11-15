"""
tests/unit/test_resample.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for multi-timeframe bar aggregation (1d -> 1w, 1M, 1Q, 1Y).
"""

from __future__ import annotations

from datetime import UTC, datetime

from analysis.resample import aggregate_bars
from core.entities import AdjustType, MarketBar, Timeframe


def make_bar(
    symbol: str = "600519.SH",
    ts: datetime | None = None,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 100.0,
    volume: float = 1000.0,
    amount: float = 100000.0,
) -> MarketBar:
    if ts is None:
        ts = datetime(2024, 1, 2, tzinfo=UTC)
    return MarketBar(
        symbol=symbol,
        timeframe=Timeframe.D1,
        adj_type=AdjustType.NONE,
        ts=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        amount=amount,
        source_id="test",
    )


def test_aggregate_d1_returns_unchanged() -> None:
    bars = [make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC))]
    res = aggregate_bars(bars, Timeframe.D1)
    assert len(res) == 1
    assert res[0].timeframe == Timeframe.D1


def test_aggregate_weekly() -> None:
    # 2024-01-02 (Tue), 2024-01-03 (Wed), 2024-01-04 (Thu), 2024-01-05 (Fri) -> Week 1
    # 2024-01-08 (Mon) -> Week 2
    bars = [
        make_bar(
            ts=datetime(2024, 1, 2, tzinfo=UTC),
            open_=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=100.0,
            amount=10000.0,
        ),
        make_bar(
            ts=datetime(2024, 1, 3, tzinfo=UTC),
            open_=102.0,
            high=110.0,
            low=101.0,
            close=108.0,
            volume=200.0,
            amount=20000.0,
        ),
        make_bar(
            ts=datetime(2024, 1, 4, tzinfo=UTC),
            open_=108.0,
            high=109.0,
            low=104.0,
            close=105.0,
            volume=150.0,
            amount=15000.0,
        ),
        make_bar(
            ts=datetime(2024, 1, 5, tzinfo=UTC),
            open_=105.0,
            high=107.0,
            low=90.0,
            close=92.0,
            volume=250.0,
            amount=25000.0,
        ),
        make_bar(
            ts=datetime(2024, 1, 8, tzinfo=UTC),
            open_=95.0,
            high=98.0,
            low=94.0,
            close=96.0,
            volume=300.0,
            amount=30000.0,
        ),
    ]

    weekly = aggregate_bars(bars, Timeframe.W1)
    assert len(weekly) == 2

    # Week 1
    w1 = weekly[0]
    assert w1.timeframe == Timeframe.W1
    assert w1.open == 100.0  # Open of first bar (Tuesday)
    assert w1.close == 92.0  # Close of last bar (Friday)
    assert w1.high == 110.0  # Max high of week
    assert w1.low == 90.0  # Min low of week
    assert w1.volume == 700.0  # Sum of volume
    assert w1.amount == 70000.0
    assert w1.ts == datetime(2024, 1, 2, tzinfo=UTC)

    # Week 2
    w2 = weekly[1]
    assert w2.open == 95.0
    assert w2.close == 96.0
    assert w2.volume == 300.0


def test_aggregate_monthly_and_quarterly() -> None:
    # Jan 2024 & Feb 2024 & Apr 2024
    bars = [
        make_bar(
            ts=datetime(2024, 1, 15, tzinfo=UTC),
            open_=10.0,
            high=12.0,
            low=9.0,
            close=11.0,
            volume=100.0,
            amount=1000.0,
        ),
        make_bar(
            ts=datetime(2024, 1, 31, tzinfo=UTC),
            open_=11.0,
            high=15.0,
            low=10.0,
            close=14.0,
            volume=200.0,
            amount=2000.0,
        ),
        make_bar(
            ts=datetime(2024, 2, 1, tzinfo=UTC),
            open_=14.0,
            high=16.0,
            low=13.0,
            close=15.0,
            volume=150.0,
            amount=1500.0,
        ),
        make_bar(
            ts=datetime(2024, 4, 10, tzinfo=UTC),
            open_=15.0,
            high=18.0,
            low=14.0,
            close=17.0,
            volume=300.0,
            amount=3000.0,
        ),
    ]

    monthly = aggregate_bars(bars, Timeframe.MN1)
    assert len(monthly) == 3
    assert monthly[0].open == 10.0
    assert monthly[0].close == 14.0
    assert monthly[0].high == 15.0
    assert monthly[0].volume == 300.0

    quarterly = aggregate_bars(bars, Timeframe.Q1)
    assert len(quarterly) == 2  # Q1 (Jan+Feb) and Q2 (Apr)
    q1 = quarterly[0]
    assert q1.open == 10.0
    assert q1.close == 15.0
    assert q1.high == 16.0
    assert q1.low == 9.0
    assert q1.volume == 450.0
