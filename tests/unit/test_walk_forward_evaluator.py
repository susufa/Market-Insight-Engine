"""
tests/unit/test_walk_forward_evaluator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the WalkForwardEvaluator and model registry admission.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.entities import Market, MarketBar, Timeframe
from models.baselines.naive import NaiveBaselinePredictor
from models.ml.lgbm_predictor import LightGBMPredictor
from models.registry import ModelRegistry
from models.validation.evaluator import WalkForwardEvaluator


@pytest.fixture
def synthetic_bars() -> list[MarketBar]:
    now = datetime(2023, 1, 1, tzinfo=UTC)
    bars: list[MarketBar] = []
    p = 100.0

    for i in range(350):
        dt = now + timedelta(days=i)
        if dt.weekday() in (5, 6):
            continue
        drift = 0.0005 + 0.015 * ((i % 11) - 5) / 5.0
        p = max(5.0, p * (1.0 + drift))
        high = p * 1.015
        low = p * 0.985
        open_p = p * 0.995
        vol = 100000.0 + (i % 7) * 15000.0

        bars.append(
            MarketBar(
                symbol="600519.SH",
                ts=dt,
                timeframe=Timeframe.D1,
                open=round(open_p, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(p, 2),
                volume=round(vol, 0),
                amount=round(vol * p, 2),
                market=Market.CN_A,
                source_id="synthetic",
            )
        )
    return bars


def test_walk_forward_evaluator_execution(synthetic_bars: list[MarketBar]) -> None:
    evaluator = WalkForwardEvaluator(
        min_train_size=120,
        test_size=30,
        gap_size=5,
        horizon=5,
    )
    lgbm = LightGBMPredictor(n_estimators=25, max_depth=3)
    baseline = NaiveBaselinePredictor()

    summary = evaluator.evaluate_model(lgbm, synthetic_bars, baseline=baseline)

    assert summary.model_name == "lightgbm_quant_model"
    assert summary.fold_count >= 2
    assert summary.sample_count > 150
    assert 0.0 <= summary.win_rate <= 1.0
    assert summary.mae > 0
    assert summary.rmse > 0
    assert summary.baseline_win_rate >= 0.0
    assert isinstance(summary.outperformed_baseline, bool)


def test_model_registry_train_and_forecast(synthetic_bars: list[MarketBar], tmp_path) -> None:
    registry = ModelRegistry(artifacts_dir=tmp_path)

    # 1. List catalog
    catalog = registry.list_models()
    assert len(catalog) >= 3
    names = [m["model_name"] for m in catalog]
    assert "naive_drift_baseline" in names
    assert "lightgbm_quant_model" in names

    # 2. Forecast generation
    pred = registry.forecast(
        symbol="600519.SH",
        bars=synthetic_bars,
        model_name="lightgbm_quant_model",
        horizon=5,
    )

    assert pred.symbol == "600519.SH"
    assert pred.horizon == 5
    assert pred.lower_bound < pred.point_estimate < pred.upper_bound
    assert "up" in pred.probabilities
    assert len(pred.disclaimer) > 0
    assert "不构成任何投资建议" in pred.disclaimer
