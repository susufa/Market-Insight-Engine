"""
models/validation/leakage_guard.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Data leakage detection and point-in-time correctness verification.

Raises DataLeakageDetectedError upon any violation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import numpy as np
import polars as pl

from core.exceptions import DataLeakageDetectedError


class DataLeakageGuard:
    """
    Automated inspector and assertions for time-series point-in-time integrity.
    """

    @staticmethod
    def assert_strict_chronology(
        train_dates: Sequence[datetime | str],
        test_dates: Sequence[datetime | str],
        label_horizon_bars: int = 0,
        calendar_dates: Sequence[datetime | str] | None = None,
    ) -> None:
        """
        Verify that all training timestamps strictly precede all test timestamps.
        If label_horizon_bars > 0 and calendar_dates is provided, verifies that
        the latest training sample's forward label window has fully expired before min(test_dates).
        """
        if not train_dates or not test_dates:
            raise DataLeakageDetectedError("Train or test sequence is empty.")

        def _to_iso(d: datetime | str) -> str:
            return d.isoformat() if isinstance(d, datetime) else str(d)

        train_isos = [_to_iso(d) for d in train_dates]
        test_isos = [_to_iso(d) for d in test_dates]

        max_train = max(train_isos)
        min_test = min(test_isos)

        if max_train >= min_test:
            raise DataLeakageDetectedError(
                f"Temporal overlap detected: max(train_date)={max_train} >= "
                f"min(test_date)={min_test}. Future data leaked into training."
            )

        if label_horizon_bars > 0 and calendar_dates:
            cal_isos = [_to_iso(d) for d in calendar_dates]
            if max_train in cal_isos:
                train_idx = cal_isos.index(max_train)
                label_end_idx = train_idx + label_horizon_bars
                if label_end_idx < len(cal_isos):
                    label_end_iso = cal_isos[label_end_idx]
                    if label_end_iso >= min_test:
                        raise DataLeakageDetectedError(
                            f"Label lookahead overlap detected: train sample at {max_train} has a "
                            f"{label_horizon_bars}-bar label horizon expiring at {label_end_iso}, "
                            f"which overlaps with test start {min_test}."
                        )

    @staticmethod
    def assert_no_future_features(
        features_df: pl.DataFrame,
        as_of: datetime,
        timestamp_col: str = "ts",
    ) -> None:
        """
        Verify that no feature row in `features_df` has a timestamp > `as_of`.
        """
        if timestamp_col not in features_df.columns:
            return

        ts_series = features_df[timestamp_col]
        # Filter rows exceeding as_of
        if ts_series.dtype == pl.Utf8:
            as_of_str = as_of.isoformat()
            future_mask = ts_series > as_of_str
        else:
            future_mask = ts_series > as_of

        future_count = future_mask.sum()
        if future_count > 0:
            raise DataLeakageDetectedError(
                f"Features contain {future_count} rows with timestamps after as_of ({as_of})."
            )

    @staticmethod
    def assert_no_target_in_features(
        feature_columns: Sequence[str],
        target_name: str = "target",
    ) -> None:
        """
        Ensure the prediction target column is not present among the features.
        """
        forbidden_substrings = [target_name.lower(), "future_", "next_", "lead_", "label"]
        for col in feature_columns:
            col_lower = col.lower()
            is_suspicious = col_lower == target_name.lower() or any(
                sub in col_lower for sub in forbidden_substrings
            )
            if is_suspicious:
                raise DataLeakageDetectedError(
                    f"Suspicious feature column '{col}' detected. Target or future indicator "
                    f"must never be passed as an explanatory variable."
                )

    @staticmethod
    def assert_scaler_isolation(
        scaler_mean: np.ndarray | float,
        train_mean: np.ndarray | float,
        tol: float = 1e-5,
    ) -> None:
        """
        Ensure standardization scaler parameters match the training set alone,
        verifying the test set was not used in preprocessing.
        """
        diff = np.max(np.abs(scaler_mean - train_mean))
        if diff > tol:
            raise DataLeakageDetectedError(
                f"Scaler mean differs from training split mean (max diff={diff:.6f} > {tol}). "
                "Global or test-inclusive fitting detected."
            )

    @staticmethod
    def inspect_lookahead_correlation(
        features: np.ndarray,
        labels: np.ndarray,
        feature_names: list[str],
        threshold: float = 0.98,
    ) -> None:
        """
        Detect accidental target leakage where a feature has near-perfect correlation
        with the future label (e.g. leaking future close price).
        """
        for idx, col in enumerate(feature_names):
            feat = features[:, idx]
            # Avoid division by zero on flat feature
            std_f = np.std(feat)
            std_l = np.std(labels)
            if std_f < 1e-9 or std_l < 1e-9:
                continue

            corr = np.corrcoef(feat, labels)[0, 1]
            if np.abs(corr) >= threshold:
                raise DataLeakageDetectedError(
                    f"Feature '{col}' exhibits suspicious correlation ({corr:.4f} >= {threshold}) "
                    f"with the future target label. Possible future information leakage."
                )
