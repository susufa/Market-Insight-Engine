"""
src/analysis/breadth.py
~~~~~~~~~~~~~~~~~~~~~~~
Market breadth and cross-sectional market statistics.

Computes:
- Advances, Declines, Flat (Unchanged)
- Advance / Decline ratios
- Median and Mean change percent
- Limit-up (>= 9.9%) and Limit-down (<= -9.9%) counts
- Return distribution histogram
- Explicit tracking of active, suspended, and missing securities
  (Strict requirement: never treat missing securities as flat)
- Survivorship bias warning when historical cross-section is derived from current universe
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from core.entities import Market


@dataclass(frozen=True)
class StockSnapshot:
    """Snapshot of a security on a given trade date."""

    symbol: str
    close: float
    prev_close: float
    volume: float
    is_suspended: bool = False
    is_missing: bool = False


@dataclass(frozen=True)
class MarketBreadthReport:
    """Comprehensive cross-sectional market breadth summary."""

    trade_date: datetime
    market: Market
    total_universe_count: int
    active_traded_count: int
    suspended_count: int
    missing_count: int
    advance_count: int
    decline_count: int
    flat_count: int
    advance_ratio: float
    decline_ratio: float
    median_change_pct: float
    mean_change_pct: float
    limit_up_count: int
    limit_down_count: int
    distribution: dict[str, int] = field(default_factory=dict)
    coverage_rate: float = 1.0
    survivorship_bias_warning: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "market": self.market.value,
            "total_universe_count": self.total_universe_count,
            "active_traded_count": self.active_traded_count,
            "suspended_count": self.suspended_count,
            "missing_count": self.missing_count,
            "advance_count": self.advance_count,
            "decline_count": self.decline_count,
            "flat_count": self.flat_count,
            "advance_ratio": round(self.advance_ratio, 4),
            "decline_ratio": round(self.decline_ratio, 4),
            "median_change_pct": round(self.median_change_pct, 4),
            "mean_change_pct": round(self.mean_change_pct, 4),
            "limit_up_count": self.limit_up_count,
            "limit_down_count": self.limit_down_count,
            "distribution": self.distribution,
            "coverage_rate": round(self.coverage_rate, 4),
            "survivorship_bias_warning": self.survivorship_bias_warning,
        }


def compute_market_breadth(
    snapshots: Sequence[StockSnapshot],
    trade_date: datetime,
    market: Market = Market.CN_A,
    is_historical_snapshot: bool = True,
) -> MarketBreadthReport:
    """
    Compute market breadth statistics from a cross-sectional snapshot of stocks.

    Parameters:
    -----------
    snapshots : Sequence[StockSnapshot]
        Cross-sectional quotes for all universe securities on trade_date.
    trade_date : datetime
        The target trading date.
    market : Market
        The market being analyzed (default: CN_A).
    is_historical_snapshot : bool
        True if the universe is from current listings applied historically
        (will trigger survivorship bias warning).
    """
    total_universe = len(snapshots)
    if total_universe == 0:
        return MarketBreadthReport(
            trade_date=trade_date,
            market=market,
            total_universe_count=0,
            active_traded_count=0,
            suspended_count=0,
            missing_count=0,
            advance_count=0,
            decline_count=0,
            flat_count=0,
            advance_ratio=0.0,
            decline_ratio=0.0,
            median_change_pct=0.0,
            mean_change_pct=0.0,
            limit_up_count=0,
            limit_down_count=0,
            distribution={
                "<-7%": 0,
                "-7%~-5%": 0,
                "-5%~-3%": 0,
                "-3%~0%": 0,
                "0%": 0,
                "0%~3%": 0,
                "3%~5%": 0,
                "5%~7%": 0,
                ">7%": 0,
            },
            coverage_rate=0.0,
            survivorship_bias_warning="No securities in universe",
        )

    active_changes: list[float] = []
    suspended_count = 0
    missing_count = 0
    advances = 0
    declines = 0
    flats = 0
    limit_ups = 0
    limit_downs = 0

    buckets = {
        "<-7%": 0,
        "-7%~-5%": 0,
        "-5%~-3%": 0,
        "-3%~0%": 0,
        "0%": 0,
        "0%~3%": 0,
        "3%~5%": 0,
        "5%~7%": 0,
        ">7%": 0,
    }

    for s in snapshots:
        if s.is_missing:
            # Crucial: missing data MUST NOT be counted as flat!
            missing_count += 1
            continue

        if s.is_suspended or s.volume <= 0:
            suspended_count += 1
            continue

        if s.prev_close <= 0:
            # Invalid reference price, treat as missing
            missing_count += 1
            continue

        pct = ((s.close - s.prev_close) / s.prev_close) * 100.0
        active_changes.append(pct)

        if pct > 0.0001:
            advances += 1
            if pct >= 9.9:
                limit_ups += 1
        elif pct < -0.0001:
            declines += 1
            if pct <= -9.9:
                limit_downs += 1
        else:
            flats += 1

        # Bucketing
        if pct < -7.0:
            buckets["<-7%"] += 1
        elif -7.0 <= pct < -5.0:
            buckets["-7%~-5%"] += 1
        elif -5.0 <= pct < -3.0:
            buckets["-5%~-3%"] += 1
        elif -3.0 <= pct < 0.0:
            buckets["-3%~0%"] += 1
        elif abs(pct) <= 0.0001:
            buckets["0%"] += 1
        elif 0.0 < pct <= 3.0:
            buckets["0%~3%"] += 1
        elif 3.0 < pct <= 5.0:
            buckets["3%~5%"] += 1
        elif 5.0 < pct <= 7.0:
            buckets["5%~7%"] += 1
        else:
            buckets[">7%"] += 1

    active_count = len(active_changes)
    total_valid = advances + declines + flats

    adv_ratio = (advances / total_valid) if total_valid > 0 else 0.0
    dec_ratio = (declines / total_valid) if total_valid > 0 else 0.0

    if active_changes:
        median_pct = float(np.median(active_changes))
        mean_pct = float(np.mean(active_changes))
    else:
        median_pct = 0.0
        mean_pct = 0.0

    coverage = (active_count + suspended_count) / total_universe if total_universe > 0 else 0.0

    warning = ""
    if is_historical_snapshot:
        warning = (
            "幸存者偏差提示：当前截面统计使用静态证券名单，未跟踪历史退市股或暂停上市成分变动，"
            "历史回测可能存在幸存者偏差。"
        )

    return MarketBreadthReport(
        trade_date=trade_date,
        market=market,
        total_universe_count=total_universe,
        active_traded_count=active_count,
        suspended_count=suspended_count,
        missing_count=missing_count,
        advance_count=advances,
        decline_count=declines,
        flat_count=flats,
        advance_ratio=adv_ratio,
        decline_ratio=dec_ratio,
        median_change_pct=median_pct,
        mean_change_pct=mean_pct,
        limit_up_count=limit_ups,
        limit_down_count=limit_downs,
        distribution=buckets,
        coverage_rate=coverage,
        survivorship_bias_warning=warning,
    )
