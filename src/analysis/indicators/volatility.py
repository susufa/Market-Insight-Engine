"""
src/analysis/indicators/volatility.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Vectorized volatility indicators: Bollinger Bands (BOLL) and Average True Range (ATR).

Formulas:
- BOLL (Bollinger Bands):
    Middle Band = SMA(Close, period)
    StdDev = Sample Standard Deviation (ddof=1) over period
    Upper Band = Middle Band + multiplier * StdDev
    Lower Band = Middle Band - multiplier * StdDev
    For t < period - 1, output is null.

- ATR (Average True Range):
    TR_0 = High_0 - Low_0
    TR_t = max(High_t - Low_t, |High_t - Close_{t-1}|, |Low_t - Close_{t-1}|)
    ATR_t = Wilder's smoothing of TR with alpha = 1 / period
    For t < period - 1, output is null.
"""

from __future__ import annotations

import polars as pl


def compute_boll(
    close: pl.Series,
    period: int = 20,
    std_dev_multiplier: float = 2.0,
) -> tuple[pl.Series, pl.Series, pl.Series]:
    """
    Compute Bollinger Bands (Upper, Middle, Lower).

    Parameters:
    -----------
    close : pl.Series
        Close price series.
    period : int
        Rolling window period (default 20).
    std_dev_multiplier : float
        Standard deviation multiplier K (default 2.0).

    Returns:
    --------
    tuple[pl.Series, pl.Series, pl.Series]:
        (upper, middle, lower)
    """
    if period < 2:
        raise ValueError(f"Period must be >= 2 for standard deviation, got {period}")

    mid = close.rolling_mean(window_size=period, min_samples=period).alias("boll_mid")
    std = close.rolling_std(window_size=period, min_samples=period, ddof=1)

    upper = (mid + std * std_dev_multiplier).alias("boll_upper")
    lower = (mid - std * std_dev_multiplier).alias("boll_lower")

    return upper, mid, lower


def compute_atr(
    high: pl.Series,
    low: pl.Series,
    close: pl.Series,
    period: int = 14,
) -> pl.Series:
    """
    Compute Average True Range (ATR).

    Parameters:
    -----------
    high : pl.Series
        High price series.
    low : pl.Series
        Low price series.
    close : pl.Series
        Close price series.
    period : int
        Lookback period (default 14).

    Returns:
    --------
    pl.Series: ATR series with nulls for t < period - 1.
    """
    if period < 1:
        raise ValueError(f"Period must be >= 1, got {period}")

    n = len(close)
    if n == 0:
        return pl.Series("atr", [], dtype=pl.Float64)

    # Shift close by 1 for prior close
    prev_close = close.shift(1)

    hl = high - low
    hc = (high - prev_close).abs()
    lc = (low - prev_close).abs()

    # True range: max(hl, hc, lc), for t=0 is hl
    df_tr = pl.DataFrame({"hl": hl, "hc": hc, "lc": lc})
    tr = df_tr.select(
        pl.max_horizontal(
            pl.col("hl"),
            pl.col("hc").fill_null(0.0),
            pl.col("lc").fill_null(0.0),
        ).alias("tr")
    ).get_column("tr")

    # Wilder's smoothing with alpha = 1 / period
    alpha = 1.0 / period
    atr_raw = tr.ewm_mean(alpha=alpha, adjust=False)

    # Mask initial period - 1 rows
    result = (
        pl.DataFrame({"atr": atr_raw})
        .with_columns(
            pl.when(pl.int_range(0, n) < period - 1)
            .then(None)
            .otherwise(pl.col("atr"))
            .alias(f"atr_{period}")
        )
        .get_column(f"atr_{period}")
    )

    return result
