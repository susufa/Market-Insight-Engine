"""
analysis/resample.py
~~~~~~~~~~~~~~~~~~~~
Trading calendar-aware multi-period K-line aggregation.
Aggregates daily (1d) OHLCV series into weekly (1w), monthly (1M),
quarterly (1Q), and yearly (1Y) bars without loss or cross-period misalignment.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.entities import MarketBar, Timeframe


def aggregate_bars(
    bars: list[MarketBar],
    target_timeframe: Timeframe,
) -> list[MarketBar]:
    """
    Aggregate daily bars into a higher timeframe (1w, 1M, 1Q, 1Y).

    Parameters
    ----------
    bars             : Daily (1d) MarketBars sorted chronologically.
    target_timeframe : Target frequency (1d, 1w, 1M, 1Q, 1Y).

    Returns
    -------
    Aggregated list of MarketBars.
    """
    if not bars:
        return []

    if target_timeframe == Timeframe.D1:
        return bars

    sorted_bars = sorted(bars, key=lambda b: b.ts)
    grouped: dict[tuple[Any, ...], list[MarketBar]] = defaultdict(list)

    for bar in sorted_bars:
        d = bar.ts.date()
        key: tuple[int, ...]
        if target_timeframe == Timeframe.W1:
            iso = d.isocalendar()
            key = (iso.year, iso.week)
        elif target_timeframe == Timeframe.MN1:
            key = (d.year, d.month)
        elif target_timeframe == Timeframe.Q1:
            quarter = (d.month - 1) // 3 + 1
            key = (d.year, quarter)
        elif target_timeframe == Timeframe.Y1:
            key = (d.year,)
        else:
            raise ValueError(f"Unsupported aggregation timeframe: {target_timeframe}")

        grouped[key].append(bar)

    aggregated: list[MarketBar] = []
    symbol = sorted_bars[0].symbol
    source_id = sorted_bars[0].source_id
    adj_type = sorted_bars[0].adj_type

    for _key, group in grouped.items():
        if not group:
            continue

        first_bar = group[0]
        last_bar = group[-1]

        open_p = first_bar.open
        close_p = last_bar.close
        high_p = max(b.high for b in group)
        low_p = min(b.low for b in group)
        volume = sum(b.volume for b in group)
        amount = sum(b.amount for b in group)

        # Standard anchor timestamp is the first trading session of the aggregated bucket
        bucket_ts = first_bar.ts

        # Zero-volume edge case (e.g. halted entire week or month)
        if volume <= 0:
            volume = 0.0
            amount = 0.0
            open_p = high_p = low_p = close_p

        agg_bar = MarketBar(
            symbol=symbol,
            timeframe=target_timeframe,
            adj_type=adj_type,
            ts=bucket_ts,
            open=open_p,
            high=high_p,
            low=low_p,
            close=close_p,
            volume=volume,
            amount=amount,
            source_id=source_id,
        )
        aggregated.append(agg_bar)

    aggregated.sort(key=lambda b: b.ts)
    return aggregated
