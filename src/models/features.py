"""
models/features.py
~~~~~~~~~~~~~~~~~~
Point-in-time quantitative feature engineering pipeline.

Builds standardized ML-ready features from K-line bars and Phase 4 indicators.
Guarantees strictly zero lookahead bias during feature extraction.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import numpy as np
import polars as pl

from analysis.indicators.engine import IndicatorEngine
from core.entities import MarketBar

FEATURE_NAMES = [
    "ret_1d",
    "ret_3d",
    "ret_5d",
    "ret_10d",
    "ma_ratio_5",
    "ma_ratio_20",
    "ma_ratio_60",
    "macd_norm",
    "rsi_14_norm",
    "kdj_j_norm",
    "boll_pos",
    "atr_ratio",
    "vol_ratio_5",
]


class FeaturePipeline:
    """
    Constructs normalized, non-lookahead features and forward targets.
    """

    def __init__(self, horizon: int = 5) -> None:
        self.horizon = horizon
        self.engine = IndicatorEngine()

    def build_feature_dataframe(
        self,
        bars: Sequence[MarketBar] | pl.DataFrame,
    ) -> pl.DataFrame:
        """
        Compute indicators and normalized features from bars.
        Returns a Polars DataFrame with columns: ts, open, high, low, close, volume,
        and all normalized features.
        """
        df_ind = self.engine.compute_all(bars)

        # Build lagged return features
        df: pl.DataFrame = df_ind.with_columns(
            [
                ((pl.col("close") / pl.col("close").shift(1)) - 1.0).alias("ret_1d"),
                ((pl.col("close") / pl.col("close").shift(3)) - 1.0).alias("ret_3d"),
                ((pl.col("close") / pl.col("close").shift(5)) - 1.0).alias("ret_5d"),
                ((pl.col("close") / pl.col("close").shift(10)) - 1.0).alias("ret_10d"),
                ((pl.col("close") / pl.col("ma_5")) - 1.0).alias("ma_ratio_5"),
                ((pl.col("close") / pl.col("ma_20")) - 1.0).alias("ma_ratio_20"),
                ((pl.col("close") / pl.col("ma_60")) - 1.0).alias("ma_ratio_60"),
                (pl.col("macd_hist") / pl.col("close")).alias("macd_norm"),
                ((pl.col("rsi_14") - 50.0) / 50.0).alias("rsi_14_norm"),
                ((pl.col("kdj_j") - 50.0) / 50.0).alias("kdj_j_norm"),
                (
                    (pl.col("close") - pl.col("boll_lower"))
                    / (pl.col("boll_upper") - pl.col("boll_lower") + 1e-6)
                ).alias("boll_pos"),
                (pl.col("atr_14") / pl.col("close")).alias("atr_ratio"),
                (
                    pl.col("volume")
                    / (pl.col("volume").rolling_mean(window_size=5, min_samples=1) + 1.0)
                ).alias("vol_ratio_5"),
            ]
        )

        return df

    def extract_training_dataset(
        self,
        bars: Sequence[MarketBar] | pl.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray, list[datetime], list[str]]:
        """
        Extract aligned feature matrix X, future return targets y, timestamps, and feature names.
        Only rows with complete lookahead targets (i.e. excluding the last `horizon` rows)
        and complete indicator warmup are returned.

        Returns
        -------
        X : np.ndarray (shape: [N, D])
        y : np.ndarray (shape: [N]) future return
        dates : list[datetime]
        feature_names : list[str]
        """
        df = self.build_feature_dataframe(bars)

        # Target: future return over `horizon` bars (Shifted backward by horizon)
        target_expr = ((pl.col("close").shift(-self.horizon) / pl.col("close")) - 1.0).alias(
            "target_return"
        )
        df_target = df.with_columns(target_expr)

        # Filter out warmup nulls and trailing horizon nulls
        clean_df = df_target.drop_nulls(subset=FEATURE_NAMES + ["target_return"])

        if clean_df.height == 0:
            return np.empty((0, len(FEATURE_NAMES))), np.empty((0,)), [], FEATURE_NAMES

        X = clean_df.select(FEATURE_NAMES).to_numpy()
        y = clean_df["target_return"].to_numpy()

        ts_raw = clean_df["ts"].to_list()
        dates: list[datetime] = []
        for t in ts_raw:
            if isinstance(t, datetime):
                dates.append(t)
            else:
                dates.append(datetime.fromisoformat(str(t).replace("Z", "+00:00")))

        return X, y, dates, FEATURE_NAMES

    def extract_inference_snapshot(
        self,
        bars: Sequence[MarketBar] | pl.DataFrame,
    ) -> tuple[np.ndarray, datetime, list[str]]:
        """
        Extract the single most recent feature row for point-in-time inference at T.
        """
        df = self.build_feature_dataframe(bars)
        clean_df = df.drop_nulls(subset=FEATURE_NAMES)
        if clean_df.height == 0:
            raise ValueError("Insufficient history to compute complete feature vector.")

        latest_row = clean_df.tail(1)
        X = latest_row.select(FEATURE_NAMES).to_numpy()
        ts_val = latest_row["ts"][0]
        if isinstance(ts_val, datetime):
            as_of = ts_val
        else:
            as_of = datetime.fromisoformat(str(ts_val).replace("Z", "+00:00"))

        return X, as_of, FEATURE_NAMES
