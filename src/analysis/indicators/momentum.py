"""
src/analysis/indicators/momentum.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Vectorized momentum indicators: MACD, RSI, and KDJ.

Formulas & Initializations:
- MACD (Moving Average Convergence Divergence):
    DIF = EMA(fast) - EMA(slow)
    DEA = EMA(signal, DIF)
    MACD_hist = bar_multiplier * (DIF - DEA) (Default bar_multiplier = 2.0 per Chinese convention)

- RSI (Relative Strength Index):
    Wilder's Smoothing: alpha = 1 / period
    U = max(C_t - C_{t-1}, 0), D = max(C_{t-1} - C_t, 0)
    AvgU_t = alpha * U_t + (1 - alpha) * AvgU_{t-1}
    AvgD_t = alpha * D_t + (1 - alpha) * AvgD_{t-1}
    RS = AvgU / AvgD
    RSI = 100 - (100 / (1 + RS))
    For t < period, output is null.

- KDJ (Stochastic Oscillator with J line):
    RSV_t = (Close_t - Low_min_N) / (High_max_N - Low_min_N) * 100
    If High_max_N == Low_min_N, RSV_t = 50.0
    K_0 = 50.0, D_0 = 50.0
    K_t = ((m1 - 1) / m1) * K_{t-1} + (1 / m1) * RSV_t
    D_t = ((m2 - 1) / m2) * D_{t-1} + (1 / m2) * K_t
    J_t = 3 * K_t - 2 * D_t
"""

from __future__ import annotations

import numpy as np
import polars as pl

from analysis.indicators.moving_averages import compute_ema


def compute_macd(
    close: pl.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    bar_multiplier: float = 2.0,
) -> tuple[pl.Series, pl.Series, pl.Series]:
    """
    Compute MACD (DIF, DEA, Histogram).

    Parameters:
    -----------
    close : pl.Series
        Close price series.
    fast : int
        Fast EMA period (default 12).
    slow : int
        Slow EMA period (default 26).
    signal : int
        Signal line EMA period (default 9).
    bar_multiplier : float
        Histogram multiplier (default 2.0 for A-share / Chinese charting software).

    Returns:
    --------
    tuple[pl.Series, pl.Series, pl.Series]:
        (dif, dea, macd_hist)
    """
    if fast >= slow:
        raise ValueError(f"Fast period ({fast}) must be < slow period ({slow})")
    if signal < 1:
        raise ValueError(f"Signal period ({signal}) must be >= 1")

    ema_fast = compute_ema(close, span=fast)
    ema_slow = compute_ema(close, span=slow)

    dif = (ema_fast - ema_slow).alias("macd_dif")
    dea = compute_ema(dif, span=signal).alias("macd_dea")
    macd_hist = ((dif - dea) * bar_multiplier).alias("macd_hist")

    return dif, dea, macd_hist


def compute_rsi(close: pl.Series, period: int = 14) -> pl.Series:
    """
    Compute Relative Strength Index (RSI) using Wilder's smoothing.

    Parameters:
    -----------
    close : pl.Series
        Close price series.
    period : int
        RSI lookback period (default 14).

    Returns:
    --------
    pl.Series: RSI series in range [0, 100], with nulls for t < period.
    """
    if period < 1:
        raise ValueError(f"Period must be >= 1, got {period}")

    n = len(close)
    if n <= period:
        return pl.Series(f"rsi_{period}", [None] * n, dtype=pl.Float64)

    alpha = 1.0 / period
    df = (
        close.to_frame("close")
        .with_columns(diff=pl.col("close").diff())
        .with_columns(
            up=pl.when(pl.col("diff") > 0).then(pl.col("diff")).otherwise(0.0),
            down=pl.when(pl.col("diff") < 0).then(-pl.col("diff")).otherwise(0.0),
        )
        .with_columns(
            avg_up=pl.col("up").ewm_mean(alpha=alpha, adjust=False),
            avg_down=pl.col("down").ewm_mean(alpha=alpha, adjust=False),
        )
    )

    rs = pl.col("avg_up") / pl.col("avg_down")

    rsi_expr = (
        pl.when(pl.col("avg_down") == 0.0)
        .then(pl.when(pl.col("avg_up") == 0.0).then(50.0).otherwise(100.0))
        .when(pl.col("avg_up") == 0.0)
        .then(0.0)
        .otherwise(100.0 - (100.0 / (1.0 + rs)))
    )

    # Invalidate values before warm-up period
    result = df.select(
        pl.when(pl.int_range(0, n) < period).then(None).otherwise(rsi_expr).alias(f"rsi_{period}")
    ).get_column(f"rsi_{period}")

    return result


def compute_kdj(
    high: pl.Series,
    low: pl.Series,
    close: pl.Series,
    n: int = 9,
    m1: int = 3,
    m2: int = 3,
) -> tuple[pl.Series, pl.Series, pl.Series]:
    """
    Compute KDJ Stochastic Indicator.

    Parameters:
    -----------
    high : pl.Series
        High price series.
    low : pl.Series
        Low price series.
    close : pl.Series
        Close price series.
    n : int
        Lookback period for RSV (default 9).
    m1 : int
        Smoothing period for K (default 3).
    m2 : int
        Smoothing period for D (default 3).

    Returns:
    --------
    tuple[pl.Series, pl.Series, pl.Series]:
        (k, d, j)
    """
    size = len(close)
    if size == 0:
        empty = pl.Series([], dtype=pl.Float64)
        return empty.alias("kdj_k"), empty.alias("kdj_d"), empty.alias("kdj_j")

    # Vectorized rolling min and max in Polars
    # min_samples=1 allows computing RSV even during warm-up
    r_low = low.rolling_min(window_size=n, min_samples=1)
    r_high = high.rolling_max(window_size=n, min_samples=1)

    r_low_arr = r_low.to_numpy()
    r_high_arr = r_high.to_numpy()
    close_arr = close.to_numpy()

    k_arr = np.empty(size, dtype=np.float64)
    d_arr = np.empty(size, dtype=np.float64)
    j_arr = np.empty(size, dtype=np.float64)

    k_prev = 50.0
    d_prev = 50.0

    k_factor = 1.0 / m1
    k_inv_factor = (m1 - 1.0) / m1

    d_factor = 1.0 / m2
    d_inv_factor = (m2 - 1.0) / m2

    for i in range(size):
        hl_diff = r_high_arr[i] - r_low_arr[i]
        rsv = ((close_arr[i] - r_low_arr[i]) / hl_diff) * 100.0 if hl_diff > 1e-12 else 50.0

        k_val = k_inv_factor * k_prev + k_factor * rsv
        d_val = d_inv_factor * d_prev + d_factor * k_val
        j_val = 3.0 * k_val - 2.0 * d_val

        k_arr[i] = k_val
        d_arr[i] = d_val
        j_arr[i] = j_val

        k_prev = k_val
        d_prev = d_val

    k_series = pl.Series("kdj_k", k_arr)
    d_series = pl.Series("kdj_d", d_arr)
    j_series = pl.Series("kdj_j", j_arr)

    return k_series, d_series, j_series
