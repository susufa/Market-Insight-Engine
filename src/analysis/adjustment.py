"""
analysis/adjustment.py
~~~~~~~~~~~~~~~~~~~~~~
Dynamic corporate action adjustment calculator (QFQ / HFQ / NONE).
Computes adjusted OHLCV price series dynamically from AdjustmentEvent records
at query time without mutating underlying unadjusted raw storage bars.
"""

from __future__ import annotations

from core.entities import AdjustmentEvent, AdjustType, MarketBar


def compute_adjusted_bars(
    bars: list[MarketBar],
    events: list[AdjustmentEvent],
    adj_type: AdjustType,
) -> list[MarketBar]:
    """
    Apply corporate action adjustments dynamically to a list of raw MarketBars.

    Parameters
    ----------
    bars     : Raw (unadjusted) MarketBars sorted chronologically.
    events   : AdjustmentEvent records for the symbol.
    adj_type : Requested adjustment type (NONE, QFQ, HFQ).

    Returns
    -------
    New list of MarketBars with adjusted prices and volumes.
    Underlying input bars are not mutated.
    """
    if not bars:
        return []

    if adj_type == AdjustType.NONE or not events:
        # Return copies with adj_type=NONE
        return [
            b.model_copy(update={"adj_type": AdjustType.NONE})
            if b.adj_type != AdjustType.NONE
            else b
            for b in bars
        ]

    # Ensure bars are sorted by timestamp
    sorted_bars = sorted(bars, key=lambda b: b.ts)
    # Ensure events are sorted by ex_date
    sorted_events = sorted(events, key=lambda ev: ev.ex_date)

    # Precompute cumulative backward-adjustment multiplier (HFQ factor) for each bar
    # Factor starts at 1.0 and multiplies at each ex-dividend date
    n = len(sorted_bars)
    hfq_factors = [1.0] * n

    # Map each ex-date to split factor
    cum_factor = 1.0
    event_idx = 0
    num_events = len(sorted_events)

    for i in range(n):
        bar_date = sorted_bars[i].ts.date()

        # Advance events up to this bar's date
        while event_idx < num_events and sorted_events[event_idx].ex_date.date() <= bar_date:
            ev = sorted_events[event_idx]
            # Prior trading day's close price P_cum
            p_cum = sorted_bars[i - 1].close if i > 0 else sorted_bars[0].open

            # Ex-dividend price formula: P_ex = (P_cum - D + R * P_r) / (1 + B + R)
            denom = 1.0 + ev.bonus_ratio + ev.rights_ratio
            numer = p_cum - ev.cash_dividend + (ev.rights_ratio * ev.rights_price)

            if denom > 0 and numer > 0 and p_cum > 0:
                p_ex = numer / denom
                split_ratio = p_cum / p_ex
                cum_factor *= split_ratio

            event_idx += 1

        hfq_factors[i] = cum_factor

    # If QFQ requested, anchor latest factor to 1.0
    latest_factor = hfq_factors[-1] if hfq_factors else 1.0
    if adj_type == AdjustType.QFQ:
        effective_factors = [f / latest_factor if latest_factor > 0 else 1.0 for f in hfq_factors]
    else:  # HFQ
        effective_factors = hfq_factors

    adjusted_bars: list[MarketBar] = []
    for bar, factor in zip(sorted_bars, effective_factors, strict=False):
        f = max(factor, 1e-6)
        adj_open = round(bar.open * f, 4)
        adj_high = round(bar.high * f, 4)
        adj_low = round(bar.low * f, 4)
        adj_close = round(bar.close * f, 4)
        adj_vol = round(bar.volume / f, 2) if f > 0 else bar.volume
        adj_amount = bar.amount  # Turnover amount is invariant under adjustment

        # Geometry guard in case of minor float rounding
        adj_high = max(adj_high, adj_open, adj_close)
        adj_low = min(adj_low, adj_open, adj_close)
        if bar.volume == 0:
            adj_open = adj_high = adj_low = adj_close
            adj_vol = 0.0
            adj_amount = 0.0

        adj_bar = bar.model_copy(
            update={
                "adj_type": adj_type,
                "open": adj_open,
                "high": adj_high,
                "low": adj_low,
                "close": adj_close,
                "volume": adj_vol,
                "amount": adj_amount,
            }
        )
        adjusted_bars.append(adj_bar)

    return adjusted_bars
