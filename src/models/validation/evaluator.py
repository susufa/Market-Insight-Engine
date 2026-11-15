"""
models/validation/evaluator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Walk-forward model evaluation and baseline benchmarking engine.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import numpy as np

from core.entities import MarketBar
from core.interfaces.predictor import BasePredictor
from models.baselines.naive import NaiveBaselinePredictor
from models.entities import ModelEvaluationSummary
from models.features import FeaturePipeline
from models.validation.leakage_guard import DataLeakageGuard
from models.validation.splitter import TimeSeriesSplitter


class WalkForwardEvaluator:
    """
    Executes walk-forward backtest evaluation across expanding/rolling folds,
    rigorously auditing point-in-time constraints and benchmarking against naive baseline.
    """

    def __init__(
        self,
        min_train_size: int = 250,
        test_size: int = 60,
        gap_size: int = 5,
        horizon: int = 5,
    ) -> None:
        self.splitter = TimeSeriesSplitter(
            min_train_size=min_train_size,
            test_size=test_size,
            gap_size=gap_size,
            mode="expanding",
        )
        self.pipeline = FeaturePipeline(horizon=horizon)
        self.guard = DataLeakageGuard()

    def evaluate_model(
        self,
        predictor: BasePredictor,
        bars: Sequence[MarketBar],
        baseline: BasePredictor | None = None,
    ) -> ModelEvaluationSummary:
        """
        Run walk-forward validation on `predictor` and compare against `baseline`.
        """
        X, y, dates, feat_names = self.pipeline.extract_training_dataset(bars)
        n_samples = len(y)
        min_req = self.splitter.min_train_size + self.splitter.gap_size + self.splitter.test_size
        if n_samples < min_req:
            raise ValueError(
                f"Insufficient sample points ({n_samples}) for walk-forward evaluation."
            )

        if baseline is None:
            baseline = NaiveBaselinePredictor()

        fold_metrics: list[dict[str, float]] = []
        baseline_metrics: list[dict[str, float]] = []

        for train_idx, test_idx in self.splitter.split(n_samples):
            train_dates = [dates[i] for i in train_idx]
            test_dates = [dates[i] for i in test_idx]

            # 1. Point-in-time anti-leakage audit
            self.guard.assert_strict_chronology(
                train_dates,
                test_dates,
                label_horizon_bars=self.pipeline.horizon,
                calendar_dates=dates,
            )

            X_train, y_train = X[train_idx], y[train_idx]
            X_test, y_test = X[test_idx], y[test_idx]

            # 2. Fit and evaluate candidate model
            train_cutoff = max(train_dates)
            predictor.fit(X_train, y_train, train_end=train_cutoff)
            eval_res = predictor.evaluate(X_test, y_test, eval_start=min(test_dates))
            fold_metrics.append(eval_res)

            # 3. Fit and evaluate baseline model
            baseline.fit(X_train, y_train, train_end=train_cutoff)
            b_res = baseline.evaluate(X_test, y_test, eval_start=min(test_dates))
            baseline_metrics.append(b_res)

        # Aggregate across folds
        avg_win_rate = float(np.mean([m.get("win_rate", 0.5) for m in fold_metrics]))
        avg_sharpe = float(np.mean([m.get("sharpe", 0.0) for m in fold_metrics]))
        avg_drawdown = float(np.mean([m.get("max_drawdown", 0.0) for m in fold_metrics]))
        avg_mae = float(np.mean([m.get("mae", 0.0) for m in fold_metrics]))
        avg_rmse = float(np.mean([m.get("rmse", 0.0) for m in fold_metrics]))

        b_win_rate = float(np.mean([m.get("win_rate", 0.5) for m in baseline_metrics]))
        b_sharpe = float(np.mean([m.get("sharpe", 0.0) for m in baseline_metrics]))

        outperformed = bool(avg_win_rate >= b_win_rate and avg_sharpe >= b_sharpe)

        return ModelEvaluationSummary(
            model_name=predictor.model_name,
            model_version=predictor.model_version,
            sample_count=n_samples,
            fold_count=len(fold_metrics),
            win_rate=round(avg_win_rate, 4),
            sharpe_ratio=round(avg_sharpe, 4),
            max_drawdown=round(avg_drawdown, 4),
            mae=round(avg_mae, 5),
            rmse=round(avg_rmse, 5),
            baseline_win_rate=round(b_win_rate, 4),
            baseline_sharpe=round(b_sharpe, 4),
            outperformed_baseline=outperformed,
            evaluation_time=datetime.utcnow(),
        )
