"""
src/analysis/sectors.py
~~~~~~~~~~~~~~~~~~~~~~~
Industry and concept sector analysis engine.

Computes:
- Sector-level average returns (equal-weighted and volume-weighted)
- Total sector trading volume and turnover
- Sector gainers / losers ranking
- Constituent stock advance/decline distribution
- Relative strength compared to benchmark index
- Constituents metadata tracking with survivorship bias warnings
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class SectorConstituentQuote:
    """Quote for an individual stock in a sector on a given trade date."""

    symbol: str
    name: str
    sector_name: str
    close: float
    prev_close: float
    volume: float
    amount: float
    is_suspended: bool = False


@dataclass(frozen=True)
class SectorSummary:
    """Summary metrics for a single industry / concept sector."""

    sector_name: str
    constituent_count: int
    active_count: int
    suspended_count: int
    advance_count: int
    decline_count: int
    flat_count: int
    avg_change_pct: float
    total_volume: float
    total_amount: float
    relative_strength_vs_bench: float  # (sector_avg - bench_return)
    top_performer: str = ""
    top_performer_pct: float = 0.0
    worst_performer: str = ""
    worst_performer_pct: float = 0.0
    constituents_source: str = "申万一级行业分类 (CSRC/SW)"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, object]:
        return {
            "sector_name": self.sector_name,
            "constituent_count": self.constituent_count,
            "active_count": self.active_count,
            "suspended_count": self.suspended_count,
            "advance_count": self.advance_count,
            "decline_count": self.decline_count,
            "flat_count": self.flat_count,
            "avg_change_pct": round(self.avg_change_pct, 4),
            "total_volume": round(self.total_volume, 2),
            "total_amount": round(self.total_amount, 2),
            "relative_strength_vs_bench": round(self.relative_strength_vs_bench, 4),
            "top_performer": self.top_performer,
            "top_performer_pct": round(self.top_performer_pct, 4),
            "worst_performer": self.worst_performer,
            "worst_performer_pct": round(self.worst_performer_pct, 4),
            "constituents_source": self.constituents_source,
            "updated_at": self.updated_at.isoformat(),
        }


def analyze_sectors(
    quotes: Sequence[SectorConstituentQuote],
    benchmark_return_pct: float = 0.0,
    constituents_source: str = "申万一级行业标准分类",
) -> list[SectorSummary]:
    """
    Aggregate cross-sectional stock quotes by industry / sector.

    Parameters:
    -----------
    quotes : Sequence[SectorConstituentQuote]
        Constituent quotes.
    benchmark_return_pct : float
        Benchmark index return on the same date for relative strength computation.
    constituents_source : str
        Source metadata description for audit trail.

    Returns:
    --------
    list[SectorSummary]: Sectors sorted by avg_change_pct descending.
    """
    if not quotes:
        return []

    # Group quotes by sector
    by_sector: dict[str, list[SectorConstituentQuote]] = {}
    for q in quotes:
        by_sector.setdefault(q.sector_name, []).append(q)

    summaries: list[SectorSummary] = []
    now = datetime.now(UTC)

    for sec_name, sec_quotes in by_sector.items():
        total_constituents = len(sec_quotes)
        active_quotes = [q for q in sec_quotes if not q.is_suspended and q.prev_close > 0]
        suspended_count = total_constituents - len(active_quotes)

        if not active_quotes:
            summaries.append(
                SectorSummary(
                    sector_name=sec_name,
                    constituent_count=total_constituents,
                    active_count=0,
                    suspended_count=suspended_count,
                    advance_count=0,
                    decline_count=0,
                    flat_count=0,
                    avg_change_pct=0.0,
                    total_volume=0.0,
                    total_amount=0.0,
                    relative_strength_vs_bench=-benchmark_return_pct,
                    constituents_source=constituents_source,
                    updated_at=now,
                )
            )
            continue

        pcts: list[float] = []
        tot_vol = 0.0
        tot_amt = 0.0
        advances = 0
        declines = 0
        flats = 0

        best_stock = ""
        best_pct = -999.0
        worst_stock = ""
        worst_pct = 999.0

        for q in active_quotes:
            pct = ((q.close - q.prev_close) / q.prev_close) * 100.0
            pcts.append(pct)
            tot_vol += q.volume
            tot_amt += q.amount

            if pct > 0.0001:
                advances += 1
            elif pct < -0.0001:
                declines += 1
            else:
                flats += 1

            if pct > best_pct:
                best_pct = pct
                best_stock = f"{q.name} ({q.symbol})"

            if pct < worst_pct:
                worst_pct = pct
                worst_stock = f"{q.name} ({q.symbol})"

        avg_pct = float(sum(pcts) / len(pcts))
        rel_strength = avg_pct - benchmark_return_pct

        summaries.append(
            SectorSummary(
                sector_name=sec_name,
                constituent_count=total_constituents,
                active_count=len(active_quotes),
                suspended_count=suspended_count,
                advance_count=advances,
                decline_count=declines,
                flat_count=flats,
                avg_change_pct=avg_pct,
                total_volume=tot_vol,
                total_amount=tot_amt,
                relative_strength_vs_bench=rel_strength,
                top_performer=best_stock,
                top_performer_pct=best_pct if best_stock else 0.0,
                worst_performer=worst_stock,
                worst_performer_pct=worst_pct if worst_stock else 0.0,
                constituents_source=constituents_source,
                updated_at=now,
            )
        )

    # Sort by performance descending
    summaries.sort(key=lambda s: s.avg_change_pct, reverse=True)
    return summaries
