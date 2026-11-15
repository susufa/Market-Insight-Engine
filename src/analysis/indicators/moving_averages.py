"""
src/analysis/indicators/moving_averages.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Vectorized Moving Average indicators implemented in Polars.

Formulas:
- SMA (Simple Moving Average):
    SMA_t = (1 / N) * sum_{i=0}^{N-1} P_{t-i}
    For t < N - 1, output is null.

- EMA (Exponential Moving Average):
    alpha = 2 / (span + 1)
    EMA_0 = P_0
    EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1}
"""

from __future__ import annotations

import polars as pl


def compute_ma(series: pl.Series, window: int) -> pl.Series:
    """
    Compute Simple Moving Average (SMA) over rolling window N.

    Parameters:
    -----------
    series : pl.Series
        Price series (float64).
    window : int
        Window size N (must be >= 1).

    Returns:
    --------
    pl.Series: SMA values with null for t < window - 1.
    """
    if window < 1:
        raise ValueError(f"Window must be >= 1, got {window}")

    return series.rolling_mean(window_size=window, min_samples=window).alias(f"ma_{window}")


def compute_ema(series: pl.Series, span: int) -> pl.Series:
    """
    Compute Exponential Moving Average (EMA) over span N.

    Parameters:
    -----------
    series : pl.Series
        Price series (float64).
    span : int
        Span N (must be >= 1). Alpha is 2 / (span + 1).

    Returns:
    --------
    pl.Series: EMA series.
    """
    if span < 1:
        raise ValueError(f"Span must be >= 1, got {span}")

    alpha = 2.0 / (span + 1.0)
    # Using adjust=False for recursive EMA: EMA_t = alpha * x_t + (1 - alpha) * EMA_{t-1}
    return series.ewm_mean(alpha=alpha, adjust=False).alias(f"ema_{span}")
