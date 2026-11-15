"""
tests/unit/test_leakage_guard.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests verifying strict point-in-time enforcement and automated detection of data leakage.
Directly verifies Gate 5 Exit Criteria:
'人为注入含未来信息特征时，系统必须抛出 DataLeakageDetectedError'
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from core.exceptions import DataLeakageDetectedError
from models.validation.leakage_guard import DataLeakageGuard


def test_chronology_guard_passes_on_valid_sequence() -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    train_dates = [now + timedelta(days=i) for i in range(100)]
    test_dates = [now + timedelta(days=i) for i in range(105, 125)]

    # Must pass without exception
    DataLeakageGuard.assert_strict_chronology(train_dates, test_dates)


def test_chronology_guard_raises_on_future_leakage() -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    # Deliberately overlap: train includes day 110, test starts at day 105
    train_dates = [now + timedelta(days=i) for i in range(111)]
    test_dates = [now + timedelta(days=i) for i in range(105, 125)]

    with pytest.raises(DataLeakageDetectedError, match="Temporal overlap detected"):
        DataLeakageGuard.assert_strict_chronology(train_dates, test_dates)


def test_guard_raises_on_future_features_beyond_as_of() -> None:
    as_of = datetime(2024, 5, 10, tzinfo=UTC)
    # Feature df contains rows past as_of (e.g. 2024-05-11)
    df = pl.DataFrame(
        {
            "ts": [
                datetime(2024, 5, 8, tzinfo=UTC),
                datetime(2024, 5, 9, tzinfo=UTC),
                datetime(2024, 5, 10, tzinfo=UTC),
                datetime(2024, 5, 11, tzinfo=UTC),  # FUTURE LEAK
            ],
            "feature_1": [1.0, 1.2, 1.1, 1.4],
        }
    )

    with pytest.raises(DataLeakageDetectedError, match="rows with timestamps after as_of"):
        DataLeakageGuard.assert_no_future_features(df, as_of)


def test_guard_raises_on_target_or_future_column_leakage() -> None:
    # Feature names accidentally contain target or future column
    bad_features = ["ret_1d", "rsi_14", "future_close_5d", "vol_ratio"]
    with pytest.raises(DataLeakageDetectedError, match="Suspicious feature column"):
        DataLeakageGuard.assert_no_target_in_features(bad_features, target_name="target_return")

    bad_features2 = ["ret_1d", "rsi_14", "target_return"]
    with pytest.raises(DataLeakageDetectedError, match="Suspicious feature column"):
        DataLeakageGuard.assert_no_target_in_features(bad_features2, target_name="target_return")


def test_guard_raises_on_scaler_fitted_across_test_data() -> None:
    train_data = np.array([10.0, 12.0, 11.0, 13.0])
    test_data = np.array([100.0, 120.0, 110.0])

    # Global scaler including test data has inflated mean
    global_mean = float(np.mean(np.concatenate([train_data, test_data])))
    train_mean = float(np.mean(train_data))

    with pytest.raises(DataLeakageDetectedError, match="Scaler mean differs from training split"):
        DataLeakageGuard.assert_scaler_isolation(global_mean, train_mean)


def test_guard_detects_artificially_injected_lookahead_correlation() -> None:
    np.random.seed(42)
    n = 100
    y_target = np.random.randn(n)

    # Legitimate features: moderate correlation with target
    feat_clean = np.random.randn(n, 2)

    # Artificially injected lookahead feature: copy of target + tiny noise
    feat_leaked = y_target + np.random.normal(0, 1e-4, size=n)

    X = np.column_stack([feat_clean, feat_leaked])
    feature_names = ["momentum", "volatility", "injected_future_feature"]

    err_pattern = "Feature 'injected_future_feature' exhibits suspicious correlation"
    with pytest.raises(DataLeakageDetectedError, match=err_pattern):
        DataLeakageGuard.inspect_lookahead_correlation(X, y_target, feature_names, threshold=0.98)
