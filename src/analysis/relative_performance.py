"""
src/analysis/relative_performance.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Statistical relative performance engine: Beta, Alpha, Correlation, and Excess Returns.

Formulas & Conventions:
- All metrics are strictly computed on RETURNS series:
    R_{stock, t} = (P_{s, t} - P_{s, t-1}) / P_{s, t-1}
    R_{bench, t} = (P_{b, t} - P_{b, t-1}) / P_{b, t-1}

- Beta (Market Risk Sensitivity):
    Beta = Cov(R_s, R_b) / Var(R_b)
    If Var(R_b) == 0, Beta = 0.0

- Pearson Correlation (r):
    r = Cov(R_s, R_b) / (sigma_s * sigma_b)
    If sigma_s == 0 or sigma_b == 0, r = 0.0

- R-Squared (Coefficient of Determination):
    R^2 = r^2

- Jensen's Alpha (Annualized):
    Annual trading days = 250
    Default risk-free rate R_f = 0.02 (2.0% annualized)
    Annualized Stock Return = (1 + mean(R_s))^250 - 1  (or mean(R_s) * 250)
    Annualized Bench Return = (1 + mean(R_b))^250 - 1
    Alpha_ann = (R_{s, ann} - R_f) - Beta * (R_{b, ann} - R_f)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from core.entities import MarketBar


@dataclass(frozen=True)
class RelativePerformanceMetrics:
    """Statistical relative performance metrics against a benchmark index."""

    symbol: str
    benchmark_symbol: str
    sample_count: int
    start_date: datetime
    end_date: datetime
    beta: float
    alpha_annualized: float
    correlation: float
    r_squared: float
    stock_annualized_return: float
    benchmark_annualized_return: float
    stock_volatility_annualized: float
    benchmark_volatility_annualized: float
    cumulative_excess_return: float

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "benchmark_symbol": self.benchmark_symbol,
            "sample_count": self.sample_count,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "beta": round(self.beta, 4),
            "alpha_annualized": round(self.alpha_annualized, 4),
            "correlation": round(self.correlation, 4),
            "r_squared": round(self.r_squared, 4),
            "stock_annualized_return": round(self.stock_annualized_return, 4),
            "benchmark_annualized_return": round(self.benchmark_annualized_return, 4),
            "stock_volatility_annualized": round(self.stock_volatility_annualized, 4),
            "benchmark_volatility_annualized": round(self.benchmark_volatility_annualized, 4),
            "cumulative_excess_return": round(self.cumulative_excess_return, 4),
        }


def compute_relative_performance(
    stock_bars: Sequence[MarketBar],
    benchmark_bars: Sequence[MarketBar],
    risk_free_rate_ann: float = 0.02,
    trading_days_per_year: int = 250,
) -> RelativePerformanceMetrics:
    """
    Compute Beta, Alpha, Correlation, and relative return statistics.

    Parameters:
    -----------
    stock_bars : Sequence[MarketBar]
        Price bars for the target stock.
    benchmark_bars : Sequence[MarketBar]
        Price bars for the benchmark index (e.g. 000001.SH / 000300.SH).
    risk_free_rate_ann : float
        Annualized risk-free rate (default: 0.02 = 2.0%).
    trading_days_per_year : int
        Annualization factor (default: 250).
    """
    if not stock_bars or not benchmark_bars:
        now = datetime.now(UTC)
        return RelativePerformanceMetrics(
            symbol=stock_bars[0].symbol if stock_bars else "",
            benchmark_symbol=benchmark_bars[0].symbol if benchmark_bars else "",
            sample_count=0,
            start_date=now,
            end_date=now,
            beta=0.0,
            alpha_annualized=0.0,
            correlation=0.0,
            r_squared=0.0,
            stock_annualized_return=0.0,
            benchmark_annualized_return=0.0,
            stock_volatility_annualized=0.0,
            benchmark_volatility_annualized=0.0,
            cumulative_excess_return=0.0,
        )

    # 1. Map timestamps to close prices
    s_map = {b.ts.date(): b.close for b in stock_bars}
    b_map = {b.ts.date(): b.close for b in benchmark_bars}

    # Common aligned trading dates sorted chronologically
    common_dates = sorted(set(s_map.keys()) & set(b_map.keys()))

    if len(common_dates) < 3:
        # Insufficient aligned samples
        first_d = common_dates[0] if common_dates else datetime.now(UTC).date()
        last_d = common_dates[-1] if common_dates else first_d
        return RelativePerformanceMetrics(
            symbol=stock_bars[0].symbol,
            benchmark_symbol=benchmark_bars[0].symbol,
            sample_count=len(common_dates),
            start_date=datetime.combine(first_d, datetime.min.time(), tzinfo=UTC),
            end_date=datetime.combine(last_d, datetime.min.time(), tzinfo=UTC),
            beta=0.0,
            alpha_annualized=0.0,
            correlation=0.0,
            r_squared=0.0,
            stock_annualized_return=0.0,
            benchmark_annualized_return=0.0,
            stock_volatility_annualized=0.0,
            benchmark_volatility_annualized=0.0,
            cumulative_excess_return=0.0,
        )

    s_prices = np.array([s_map[d] for d in common_dates], dtype=np.float64)
    b_prices = np.array([b_map[d] for d in common_dates], dtype=np.float64)

    # 2. Compute simple percentage returns
    s_ret = (s_prices[1:] - s_prices[:-1]) / s_prices[:-1]
    b_ret = (b_prices[1:] - b_prices[:-1]) / b_prices[:-1]

    n_samples = len(s_ret)

    # 3. Variance & Covariance
    var_b = float(np.var(b_ret, ddof=1))
    std_s = float(np.std(s_ret, ddof=1))
    std_b = float(np.std(b_ret, ddof=1))

    if var_b > 1e-12:
        cov_matrix = np.cov(s_ret, b_ret, ddof=1)
        cov_sb = float(cov_matrix[0, 1])
        beta = cov_sb / var_b
    else:
        cov_sb = 0.0
        beta = 0.0

    # Correlation
    if std_s > 1e-12 and std_b > 1e-12:
        corr = float(cov_sb / (std_s * std_b))
        corr = max(-1.0, min(1.0, corr))
    else:
        corr = 0.0

    r_squared = float(corr**2)

    # 4. Annualized returns and Jensen's Alpha
    mean_s = float(np.mean(s_ret))
    mean_b = float(np.mean(b_ret))

    s_ann_ret = mean_s * trading_days_per_year
    b_ann_ret = mean_b * trading_days_per_year

    s_ann_vol = std_s * np.sqrt(trading_days_per_year)
    b_ann_vol = std_b * np.sqrt(trading_days_per_year)

    alpha_ann = (s_ann_ret - risk_free_rate_ann) - beta * (b_ann_ret - risk_free_rate_ann)

    # Cumulative excess return
    cum_s = float(np.prod(1.0 + s_ret) - 1.0)
    cum_b = float(np.prod(1.0 + b_ret) - 1.0)
    cum_excess = cum_s - cum_b

    start_dt = datetime.combine(common_dates[0], datetime.min.time(), tzinfo=UTC)
    end_dt = datetime.combine(common_dates[-1], datetime.min.time(), tzinfo=UTC)

    return RelativePerformanceMetrics(
        symbol=stock_bars[0].symbol,
        benchmark_symbol=benchmark_bars[0].symbol,
        sample_count=n_samples,
        start_date=start_dt,
        end_date=end_dt,
        beta=beta,
        alpha_annualized=alpha_ann,
        correlation=corr,
        r_squared=r_squared,
        stock_annualized_return=s_ann_ret,
        benchmark_annualized_return=b_ann_ret,
        stock_volatility_annualized=s_ann_vol,
        benchmark_volatility_annualized=b_ann_vol,
        cumulative_excess_return=cum_excess,
    )
