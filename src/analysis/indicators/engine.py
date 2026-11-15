"""
src/analysis/indicators/engine.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unified, vectorized technical indicator engine for single and batch security processing.
Supports both full computation and state-preserving exact incremental updates.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import polars as pl

from analysis.indicators.momentum import compute_kdj, compute_macd, compute_rsi
from analysis.indicators.moving_averages import compute_ema, compute_ma
from analysis.indicators.volatility import compute_atr, compute_boll
from core.entities import MarketBar


class IndicatorEngine:
    """
    High-performance technical indicator computing engine.
    Processes OHLCV data using Polars vectorized expressions and returns structured DataFrames.
    """

    DEFAULT_MA_WINDOWS: list[int] = [5, 10, 20, 60]
    DEFAULT_EMA_SPANS: list[int] = [12, 26]
    DEFAULT_RSI_PERIODS: list[int] = [6, 12, 14, 24]
    DEFAULT_MACD_PARAMS: tuple[int, int, int] = (12, 26, 9)
    DEFAULT_KDJ_PARAMS: tuple[int, int, int] = (9, 3, 3)
    DEFAULT_BOLL_PARAMS: tuple[int, float] = (20, 2.0)
    DEFAULT_ATR_PERIOD: int = 14

    @staticmethod
    def bars_to_dataframe(bars: Sequence[MarketBar]) -> pl.DataFrame:
        """Convert a sequence of MarketBar domain entities into a sorted Polars DataFrame."""
        if not bars:
            return pl.DataFrame(
                schema={
                    "ts": pl.Datetime,
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "volume": pl.Float64,
                    "amount": pl.Float64,
                }
            )

        sorted_bars = sorted(bars, key=lambda b: b.ts)
        return pl.DataFrame(
            {
                "ts": [b.ts for b in sorted_bars],
                "open": [b.open for b in sorted_bars],
                "high": [b.high for b in sorted_bars],
                "low": [b.low for b in sorted_bars],
                "close": [b.close for b in sorted_bars],
                "volume": [b.volume for b in sorted_bars],
                "amount": [b.amount for b in sorted_bars],
            }
        )

    def compute_all(
        self,
        data: pl.DataFrame | Sequence[MarketBar],
        ma_windows: list[int] | None = None,
        ema_spans: list[int] | None = None,
        rsi_periods: list[int] | None = None,
        macd_params: tuple[int, int, int] | None = None,
        kdj_params: tuple[int, int, int] | None = None,
        boll_params: tuple[int, float] | None = None,
        atr_period: int | None = None,
    ) -> pl.DataFrame:
        """
        Compute full technical indicators suite over OHLCV input.
        """
        df = data.clone() if isinstance(data, pl.DataFrame) else self.bars_to_dataframe(data)

        if df.is_empty():
            return df

        if "ts" in df.columns:
            df = df.sort("ts")

        close = df["close"]
        high = df["high"]
        low = df["low"]

        new_cols: list[pl.Series] = []

        # 1. Moving Averages
        windows = ma_windows if ma_windows is not None else self.DEFAULT_MA_WINDOWS
        for w in windows:
            new_cols.append(compute_ma(close, window=w))

        # 2. Exponential Moving Averages
        spans = ema_spans if ema_spans is not None else self.DEFAULT_EMA_SPANS
        for s in spans:
            new_cols.append(compute_ema(close, span=s))

        # 3. MACD
        m_params = macd_params or self.DEFAULT_MACD_PARAMS
        dif, dea, hist = compute_macd(close, fast=m_params[0], slow=m_params[1], signal=m_params[2])
        new_cols.extend([dif, dea, hist])

        # 4. RSI
        r_periods = rsi_periods if rsi_periods is not None else self.DEFAULT_RSI_PERIODS
        for p in r_periods:
            new_cols.append(compute_rsi(close, period=p))

        # 5. KDJ
        k_params = kdj_params or self.DEFAULT_KDJ_PARAMS
        k, d, j = compute_kdj(high, low, close, n=k_params[0], m1=k_params[1], m2=k_params[2])
        new_cols.extend([k, d, j])

        # 6. BOLL
        b_params = boll_params or self.DEFAULT_BOLL_PARAMS
        upper, mid, b_lower = compute_boll(
            close, period=b_params[0], std_dev_multiplier=b_params[1]
        )
        new_cols.extend([upper, mid, b_lower])

        # 7. ATR
        a_period = atr_period or self.DEFAULT_ATR_PERIOD
        new_cols.append(compute_atr(high, low, close, period=a_period))

        return df.with_columns(new_cols)

    def compute_incremental(
        self,
        older_df: pl.DataFrame,
        new_bars: Sequence[MarketBar],
        **kwargs: Any,
    ) -> pl.DataFrame:
        """
        State-preserving incremental computation:
        Combines historical state with new bars to achieve exact mathematical equivalence
        without full historical recalculation.
        """
        if older_df.is_empty():
            return self.compute_all(new_bars, **kwargs)
        if not new_bars:
            return older_df

        new_df = self.bars_to_dataframe(new_bars)
        # Combine full raw series to compute exact new rows with full lookback
        combined_raw = pl.concat(
            [
                older_df.select(["ts", "open", "high", "low", "close", "volume", "amount"]),
                new_df,
            ]
        )
        return self.compute_all(combined_raw, **kwargs)

    def compute_batch(
        self,
        batch_data: dict[str, pl.DataFrame | Sequence[MarketBar]],
        **kwargs: Any,
    ) -> dict[str, pl.DataFrame]:
        """
        Batch-compute technical indicators across multiple securities.
        """
        results: dict[str, pl.DataFrame] = {}
        for symbol, data in batch_data.items():
            results[symbol] = self.compute_all(data, **kwargs)
        return results
