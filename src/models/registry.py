"""
models/registry.py
~~~~~~~~~~~~~~~~~~
Model registry, lifecycle coordinator, and inference service.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from core.entities import DataOrigin, MarketBar, Timeframe
from core.interfaces.predictor import BasePredictor
from models.baselines.linear import MovingAverageLinearPredictor
from models.baselines.naive import NaiveBaselinePredictor
from models.entities import ModelEvaluationSummary, PredictionResult
from models.features import FeaturePipeline
from models.ml.lgbm_predictor import LightGBMPredictor
from models.validation.evaluator import WalkForwardEvaluator


class ModelRegistry:
    """
    Central registry for predictive models, enforcing baseline comparison
    and point-in-time prediction generation.
    """

    def __init__(self, artifacts_dir: Path | None = None) -> None:
        self.artifacts_dir = artifacts_dir or Path("data/models")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self._models: dict[str, BasePredictor] = {}
        self._evaluations: dict[str, ModelEvaluationSummary] = {}
        self._register_default_models()

    def _register_default_models(self) -> None:
        """Register the built-in baseline and ML predictors."""
        naive = NaiveBaselinePredictor()
        linear = MovingAverageLinearPredictor()
        lgbm = LightGBMPredictor()

        self._models[naive.model_name] = naive
        self._models[linear.model_name] = linear
        self._models[lgbm.model_name] = lgbm

    def list_models(self) -> list[dict[str, Any]]:
        """Return catalog of available predictive models."""
        items = []
        for name, model in self._models.items():
            eval_info = self._evaluations.get(name)
            items.append(
                {
                    "model_name": model.model_name,
                    "model_version": model.model_version,
                    "description": model.task_description,
                    "is_baseline": "baseline" in name,
                    "evaluation": eval_info.model_dump() if eval_info else None,
                }
            )
        return items

    def get_model(self, name: str) -> BasePredictor:
        if name not in self._models:
            models_list = list(self._models.keys())
            raise KeyError(f"Predictive model '{name}' not found. Available: {models_list}")
        return self._models[name]

    def save_model(self, model_name: str, directory: Path | None = None) -> Path:
        """Persist model artifacts and metadata to disk."""
        target_dir = directory or self.artifacts_dir
        model = self.get_model(model_name)
        if hasattr(model, "save"):
            return model.save(target_dir)
        raise NotImplementedError(f"Model {model_name} does not implement save()")

    def load_model(self, model_name: str, directory: Path | None = None) -> None:
        """Load model artifacts and metadata from disk."""
        target_dir = directory or self.artifacts_dir
        model = self.get_model(model_name)
        if hasattr(model, "load"):
            model.load(target_dir)
            return
        raise NotImplementedError(f"Model {model_name} does not implement load()")

    def train_and_evaluate(
        self,
        model_name: str,
        bars: Sequence[MarketBar],
        horizon: int = 5,
    ) -> ModelEvaluationSummary:
        """
        Train the model using walk-forward cross validation and compare with baseline.
        """
        model = self.get_model(model_name)
        evaluator = WalkForwardEvaluator(
            min_train_size=200, test_size=50, gap_size=horizon, horizon=horizon
        )
        summary = evaluator.evaluate_model(model, bars)

        sample_bar = bars[0] if bars else None
        data_origin = getattr(sample_bar, "data_origin", DataOrigin.UNKNOWN)
        src_id = getattr(sample_bar, "source_id", "")
        is_synthetic = bool(data_origin == DataOrigin.SYNTHETIC_TEST or src_id == "mock_synth")
        data_source = getattr(sample_bar, "source_interface", "") or src_id or "storage"

        summary.data_origin = data_origin
        summary.is_synthetic = is_synthetic
        summary.data_source = data_source
        if is_synthetic:
            summary.warning_message = "⚠️ 当前回测基于离线合成数据，仅用于演示，非真实模型指标。"

        self._evaluations[model_name] = summary

        # Final fit on entire available series for real-time inference
        pipeline = FeaturePipeline(horizon=horizon)
        X, y, dates, _ = pipeline.extract_training_dataset(bars)
        if len(y) > 0:
            model.fit(X, y, train_end=max(dates))

        return summary

    def forecast(
        self,
        symbol: str,
        bars: Sequence[MarketBar],
        model_name: str = "lightgbm_quant_model",
        horizon: int = 5,
        timeframe: Timeframe = Timeframe.D1,
    ) -> PredictionResult:
        """
        Generate a point-in-time prediction for `symbol` at the latest available bar.
        """
        model = self.get_model(model_name)
        pipeline = FeaturePipeline(horizon=horizon)

        # Extract features for current bar snapshot
        X_snapshot, as_of, feat_names = pipeline.extract_inference_snapshot(bars)

        # Ensure model is fitted; if not fitted yet, auto-fit on available history
        if not getattr(model, "_fitted", True):
            X_train, y_train, dates, _ = pipeline.extract_training_dataset(bars)
            if len(y_train) < 30:
                raise ValueError("Insufficient historical bars to train predictor.")
            model.fit(X_train, y_train, train_end=max(dates))

        # Generate prediction dictionary from model interface
        pred_dict = model.predict(
            X_snapshot,
            as_of=as_of,
            horizon=horizon,
            timeframe=timeframe,
        )

        eval_summary = self._evaluations.get(model_name)
        test_eval = (
            {
                "win_rate": eval_summary.win_rate,
                "sharpe": eval_summary.sharpe_ratio,
                "max_drawdown": eval_summary.max_drawdown,
                "mae": eval_summary.mae,
            }
            if eval_summary
            else {}
        )

        sample_bar = bars[0] if bars else None
        data_origin = getattr(sample_bar, "data_origin", DataOrigin.UNKNOWN)
        src_id = getattr(sample_bar, "source_id", "")
        is_synthetic = bool(data_origin == DataOrigin.SYNTHETIC_TEST or src_id == "mock_synth")
        data_source = getattr(sample_bar, "source_interface", "") or src_id or "storage"
        warning_msg = (
            "⚠️ 当前预测基于离线合成数据，仅用于演示，非实盘推断。" if is_synthetic else None
        )

        first_ts = bars[0].ts.isoformat() if bars else ""
        last_ts = as_of.isoformat()

        return PredictionResult(
            symbol=symbol,
            as_of=as_of,
            horizon=horizon,
            timeframe=timeframe.value if hasattr(timeframe, "value") else str(timeframe),
            model_name=model.model_name,
            model_version=model.model_version,
            point_estimate=pred_dict["point_estimate"],
            lower_bound=pred_dict["lower_bound"],
            upper_bound=pred_dict["upper_bound"],
            confidence=pred_dict.get("confidence", 0.80),
            probabilities=pred_dict.get("probabilities", {}),
            feature_importance=pred_dict.get("feature_importance", {}),
            train_date_range=(first_ts, last_ts),
            test_evaluation=test_eval,
            disclaimer="学术研究与量化回测参考，不构成任何投资建议或确定性交易依据",
            data_origin=data_origin,
            is_synthetic=is_synthetic,
            data_source=data_source,
            warning_message=warning_msg,
        )
