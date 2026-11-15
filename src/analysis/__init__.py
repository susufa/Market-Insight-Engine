"""analysis package – indicators, breadth, sectors, relative performance, and caching."""

from analysis.adjustment import compute_adjusted_bars
from analysis.breadth import MarketBreadthReport, StockSnapshot, compute_market_breadth
from analysis.cache import AnalyticsCacheManager
from analysis.indicators import (
    IndicatorEngine,
    compute_atr,
    compute_boll,
    compute_ema,
    compute_kdj,
    compute_ma,
    compute_macd,
    compute_rsi,
)
from analysis.relative_performance import (
    RelativePerformanceMetrics,
    compute_relative_performance,
)
from analysis.resample import aggregate_bars
from analysis.sectors import SectorConstituentQuote, SectorSummary, analyze_sectors

__all__ = [
    "compute_adjusted_bars",
    "aggregate_bars",
    "IndicatorEngine",
    "compute_ma",
    "compute_ema",
    "compute_macd",
    "compute_rsi",
    "compute_kdj",
    "compute_boll",
    "compute_atr",
    "StockSnapshot",
    "MarketBreadthReport",
    "compute_market_breadth",
    "SectorConstituentQuote",
    "SectorSummary",
    "analyze_sectors",
    "RelativePerformanceMetrics",
    "compute_relative_performance",
    "AnalyticsCacheManager",
]
