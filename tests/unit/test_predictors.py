"""
tests/unit/test_predictors.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for baseline and ML predictor models:
- NaiveBaselinePredictor
- MovingAverageLinearPredictor
- LightGBMPredictor
Verifies point estimate, uncertainty bounds, probability distribution, and serialisation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from core.entities import Timeframe
from models.baselines.linear import MovingAverageLinearPredictor
from models.baselines.naive import NaiveBaselinePredictor
from models.ml.lgbm_predictor import LightGBMPredictor


@pytest.fixture
def synthetic_data() -> tuple[np.ndarray, np.ndarray, datetime]:
    np.random.seed(42)
    n = 200
    p = 5
    X = np.random.randn(n, p)
    # Ground truth: y depends on features 0 and 1 with positive drift
    y = 0.005 + 0.02 * X[:, 0] - 0.015 * X[:, 1] + np.random.normal(0, 0.01, size=n)
    as_of = datetime(2024, 6, 1, tzinfo=UTC)
    return X, y, as_of


def test_naive_baseline_lifecycle(
    synthetic_data: tuple[np.ndarray, np.ndarray, datetime],
    tmp_path: Path,
) -> None:
    X, y, as_of = synthetic_data
    model = NaiveBaselinePredictor()

    assert model.model_name == "naive_drift_baseline"
    model.fit(X, y, train_end=as_of)

    # 1. Prediction structure check
    res = model.predict(X[-1:], as_of=as_of, horizon=5, timeframe=Timeframe.D1)
    assert "point_estimate" in res
    assert "lower_bound" in res
    assert "upper_bound" in res
    assert res["lower_bound"] < res["point_estimate"] < res["upper_bound"]

    # 2. Probability check
    probs = res["probabilities"]
    assert "up" in probs and "flat" in probs and "down" in probs
    assert 0.99 <= (probs["up"] + probs["flat"] + probs["down"]) <= 1.01

    # 3. Evaluation check
    eval_metrics = model.evaluate(X, y, eval_start=as_of)
    assert "win_rate" in eval_metrics
    assert "mae" in eval_metrics

    # 4. Save and load
    save_path = model.save(tmp_path)
    assert save_path.exists()

    loaded_model = NaiveBaselinePredictor()
    loaded_model.load(tmp_path)
    res_loaded = loaded_model.predict(X[-1:], as_of=as_of, horizon=5, timeframe=Timeframe.D1)
    assert res_loaded["point_estimate"] == res["point_estimate"]


def test_linear_baseline_lifecycle(
    synthetic_data: tuple[np.ndarray, np.ndarray, datetime],
    tmp_path: Path,
) -> None:
    X, y, as_of = synthetic_data
    model = MovingAverageLinearPredictor(alpha=0.5)

    assert model.model_name == "ridge_linear_baseline"
    model.fit(X, y, train_end=as_of)

    res = model.predict(X[-1:], as_of=as_of, horizon=5, timeframe=Timeframe.D1)
    assert res["lower_bound"] < res["point_estimate"] < res["upper_bound"]
    assert len(res["feature_importance"]) == X.shape[1]

    eval_metrics = model.evaluate(X, y, eval_start=as_of)
    assert eval_metrics["mae"] > 0
    assert 0.0 <= eval_metrics["win_rate"] <= 1.0

    save_path = model.save(tmp_path)
    assert save_path.exists()

    loaded_model = MovingAverageLinearPredictor()
    loaded_model.load(tmp_path)
    res_loaded = loaded_model.predict(X[-1:], as_of=as_of, horizon=5, timeframe=Timeframe.D1)
    assert abs(res_loaded["point_estimate"] - res["point_estimate"]) < 1e-5


def test_lightgbm_predictor_lifecycle(
    synthetic_data: tuple[np.ndarray, np.ndarray, datetime],
    tmp_path: Path,
) -> None:
    X, y, as_of = synthetic_data
    model = LightGBMPredictor(n_estimators=30, learning_rate=0.05, max_depth=3)

    assert model.model_name == "lightgbm_quant_model"
    model.fit(X, y, train_end=as_of)

    res = model.predict(X[-1:], as_of=as_of, horizon=5, timeframe=Timeframe.D1)
    assert res["lower_bound"] < res["point_estimate"] < res["upper_bound"]
    assert "probabilities" in res
    probs = res["probabilities"]
    assert 0.98 <= (probs["up"] + probs["flat"] + probs["down"]) <= 1.02

    # Feature importance present
    assert len(res["feature_importance"]) > 0

    eval_metrics = model.evaluate(X, y, eval_start=as_of)
    assert eval_metrics["mae"] > 0
    assert 0.0 <= eval_metrics["win_rate"] <= 1.0
    assert "sharpe" in eval_metrics
    assert "max_drawdown" in eval_metrics

    # Save & Load
    save_path = model.save(tmp_path)
    assert save_path.exists()

    loaded_model = LightGBMPredictor()
    loaded_model.load(tmp_path)
    res_loaded = loaded_model.predict(X[-1:], as_of=as_of, horizon=5, timeframe=Timeframe.D1)
    assert abs(res_loaded["point_estimate"] - res["point_estimate"]) < 1e-4
