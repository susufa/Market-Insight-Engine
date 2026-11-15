"""
tests/unit/test_adjustment.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for dynamic corporate action adjustment calculations (QFQ / HFQ / NONE).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from analysis.adjustment import compute_adjusted_bars
from core.entities import (
    AdjustmentEvent,
    AdjustType,
    MarketBar,
    Timeframe,
)


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


def test_adjustment_none_returns_raw() -> None:
    t1 = datetime(2024, 1, 2, tzinfo=UTC)
    raw_bars = [make_bar(ts=t1, close=100.0)]
    events = [
        AdjustmentEvent(
            symbol="600519.SH",
            ex_date=datetime(2024, 1, 3, tzinfo=UTC),
            cash_dividend=10.0,
            source_id="test",
        )
    ]
    res = compute_adjusted_bars(raw_bars, events, AdjustType.NONE)
    assert len(res) == 1
    assert res[0].close == 100.0
    assert res[0].adj_type == AdjustType.NONE


def test_adjustment_qfq_cash_dividend() -> None:
    """
    Day 1: Close = 100.0
    Day 2 (Ex-date): Cash dividend = 10.0 per share.
    P_ex = 100 - 10 = 90.0.
    Split ratio = 100 / 90.
    QFQ anchors Day 2 factor to 1.0, Day 1 factor to 90/100 = 0.9.
    Day 1 QFQ close = 100 * 0.9 = 90.0.
    """
    t1 = datetime(2024, 1, 2, tzinfo=UTC)
    t2 = datetime(2024, 1, 3, tzinfo=UTC)
    raw_bars = [
        make_bar(ts=t1, open_=100.0, high=105.0, low=95.0, close=100.0),
        make_bar(ts=t2, open_=90.0, high=92.0, low=88.0, close=91.0),
    ]
    events = [
        AdjustmentEvent(
            symbol="600519.SH",
            ex_date=t2,
            cash_dividend=10.0,
            bonus_ratio=0.0,
            source_id="test",
        )
    ]

    qfq_bars = compute_adjusted_bars(raw_bars, events, AdjustType.QFQ)
    assert len(qfq_bars) == 2
    # Day 1 adjusted down
    assert qfq_bars[0].close == pytest.approx(90.0, abs=0.01)
    # Day 2 latest price anchored
    assert qfq_bars[1].close == pytest.approx(91.0, abs=0.01)
    # Ensure underlying input was not mutated
    assert raw_bars[0].close == 100.0


def test_adjustment_hfq_bonus_shares() -> None:
    """
    Day 1: Close = 100.0
    Day 2: 10 送 10 (bonus_ratio = 1.0).
    P_ex = 100 / (1 + 1) = 50.0.
    HFQ anchors Day 1 factor to 1.0, Day 2 factor to 100 / 50 = 2.0.
    Day 2 raw close = 50.0 -> HFQ close = 50.0 * 2.0 = 100.0.
    """
    t1 = datetime(2024, 1, 2, tzinfo=UTC)
    t2 = datetime(2024, 1, 3, tzinfo=UTC)
    raw_bars = [
        make_bar(ts=t1, open_=100.0, high=105.0, low=95.0, close=100.0),
        make_bar(ts=t2, open_=50.0, high=52.0, low=48.0, close=50.0),
    ]
    events = [
        AdjustmentEvent(
            symbol="600519.SH",
            ex_date=t2,
            bonus_ratio=1.0,
            source_id="test",
        )
    ]

    hfq_bars = compute_adjusted_bars(raw_bars, events, AdjustType.HFQ)
    assert len(hfq_bars) == 2
    assert hfq_bars[0].close == pytest.approx(100.0, abs=0.01)
    assert hfq_bars[1].close == pytest.approx(100.0, abs=0.01)
    assert hfq_bars[1].adj_type == AdjustType.HFQ
