"""
tests/unit/test_data_provenance_and_isolation.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for Step 5 Second Acceptance:
- Data origin tracking & provenance fields
- Mock data isolation & fallback prevention
- Splitter monotonic date assertions
- Anti-leakage guard label horizon checks
- PredictionResult boundary and probability validations
- Real A-share data training and inference verification
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from fastapi import HTTPException

from api.v1.prediction import _fetch_bars_for_symbol
from core.entities import (
    DataOrigin,
)
from core.exceptions import DataLeakageDetectedError
from models.entities import PredictionResult
from models.ml.lgbm_predictor import LightGBMPredictor
from models.validation.leakage_guard import DataLeakageGuard
from models.validation.splitter import TimeSeriesSplitter
from storage.composite_engine import CompositeStorageEngine


def test_prediction_result_validation() -> None:
    """Test PredictionResult bounds and probability sum validation."""
    now = datetime.now(UTC)

    # Valid result
    res = PredictionResult(
        symbol="600519.SH",
        as_of=now,
        horizon=5,
        model_name="lightgbm",
        model_version="1.0.0",
        point_estimate=0.02,
        lower_bound=-0.01,
        upper_bound=0.05,
        probabilities={"up": 0.50, "flat": 0.30, "down": 0.20},
        data_origin=DataOrigin.REAL_PROVIDER,
        is_synthetic=False,
    )
    assert res.point_estimate == 0.02
    assert res.data_origin == DataOrigin.REAL_PROVIDER
    assert not res.is_synthetic

    # Invalid bounds: lower > point_estimate
    with pytest.raises(ValueError, match="lower_bound"):
        PredictionResult(
            symbol="600519.SH",
            as_of=now,
            horizon=5,
            model_name="lightgbm",
            model_version="1.0.0",
            point_estimate=0.02,
            lower_bound=0.03,
            upper_bound=0.05,
        )

    # Invalid bounds: upper < point_estimate
    with pytest.raises(ValueError, match="upper_bound"):
        PredictionResult(
            symbol="600519.SH",
            as_of=now,
            horizon=5,
            model_name="lightgbm",
            model_version="1.0.0",
            point_estimate=0.02,
            lower_bound=-0.01,
            upper_bound=0.01,
        )

    # Invalid probability sum: sum = 1.30 (outside [0.95, 1.05])
    with pytest.raises(ValueError, match="Probabilities must sum to ~1.0"):
        PredictionResult(
            symbol="600519.SH",
            as_of=now,
            horizon=5,
            model_name="lightgbm",
            model_version="1.0.0",
            point_estimate=0.02,
            lower_bound=-0.01,
            upper_bound=0.05,
            probabilities={"up": 0.70, "flat": 0.30, "down": 0.30},
        )


def test_splitter_monotonic_date_validation() -> None:
    """TimeSeriesSplitter.split_by_dates must reject unordered date sequences."""
    splitter = TimeSeriesSplitter(min_train_size=10, test_size=5, gap_size=2)
    now = datetime(2023, 1, 1, tzinfo=UTC)
    dates = [now + timedelta(days=i) for i in range(30)]

    # Strictly monotonic: should work
    splits = list(splitter.split_by_dates(dates))
    assert len(splits) > 0

    # Unordered / inverted sequence: must raise ValueError
    unordered_dates = list(dates)
    unordered_dates[10], unordered_dates[15] = unordered_dates[15], unordered_dates[10]
    with pytest.raises(ValueError, match="Input dates must be strictly monotonically increasing"):
        list(splitter.split_by_dates(unordered_dates))


def test_leakage_guard_label_horizon_overlap() -> None:
    """DataLeakageGuard must catch label window leakage into test set."""
    cal_dates = [datetime(2023, 1, i + 1, tzinfo=UTC) for i in range(20)]
    train_dates = cal_dates[:10]  # indices 0..9, max is Jan 10
    test_dates = cal_dates[12:16]  # indices 12..15, min is Jan 13

    # Horizon = 2: label ends Jan 12 < test Jan 13 -> No leak
    DataLeakageGuard.assert_strict_chronology(
        train_dates, test_dates, label_horizon_bars=2, calendar_dates=cal_dates
    )

    # Horizon = 5: label ends Jan 15 >= test Jan 13 -> Leak detected!
    with pytest.raises(DataLeakageDetectedError, match="Label lookahead overlap detected"):
        DataLeakageGuard.assert_strict_chronology(
            train_dates, test_dates, label_horizon_bars=5, calendar_dates=cal_dates
        )


@pytest.mark.asyncio
async def test_mock_isolation_and_404_on_missing_symbol() -> None:
    """Verify backend returns 404 when storage has no data and allow_synthetic=False."""
    engine = CompositeStorageEngine()
    await engine.initialise()

    # Missing symbol with default allow_synthetic=False must raise 404
    with pytest.raises(HTTPException) as exc_info:
        await _fetch_bars_for_symbol(engine, "NON_EXISTENT_999.SH", allow_synthetic=False)
    assert exc_info.value.status_code == 404
    assert "No real historical bar data found" in exc_info.value.detail

    # Missing symbol with allow_synthetic=True returns synthetic bars tagged properly
    synth_bars = await _fetch_bars_for_symbol(engine, "NON_EXISTENT_999.SH", allow_synthetic=True)
    assert len(synth_bars) > 50
    assert synth_bars[0].data_origin == DataOrigin.SYNTHETIC_TEST
    assert synth_bars[0].source_id == "mock_synth"


@pytest.mark.asyncio
async def test_real_moutai_data_ingestion_and_provenance() -> None:
    """Verify real Kweichow Moutai bars in production store have genuine provenance."""
    engine = CompositeStorageEngine()
    await engine.initialise()

    bars = await _fetch_bars_for_symbol(engine, "600519.SH", allow_synthetic=False)
    assert len(bars) >= 400
    assert bars[0].data_origin == DataOrigin.REAL_PROVIDER
    assert bars[0].source_interface == "akshare:stock_zh_a_daily"
    assert len(bars[0].checksum) > 0


def test_lgbm_long_only_and_friction_evaluation() -> None:
    """Verify LightGBMPredictor evaluate applies long-only constraint and friction."""
    model = LightGBMPredictor(n_estimators=10)
    np.random.seed(42)
    X = np.random.randn(100, 5)
    y = np.random.randn(100) * 0.02
    model.fit(X, y)

    res = model.evaluate(X, y, long_only=True, friction_bps=25.0, horizon=5)
    assert "win_rate" in res
    assert "sharpe" in res
    assert "max_drawdown" in res
    assert isinstance(res["sharpe"], float)
