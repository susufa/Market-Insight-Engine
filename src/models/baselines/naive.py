"""
models/baselines/naive.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Baseline naive statistical model (Random Walk with Drift).
Serves as the mandatory performance benchmark floor for all advanced ML models.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scipy import stats

from core.entities import Timeframe
from core.interfaces.predictor import BasePredictor


class NaiveBaselinePredictor(BasePredictor):
    """
    Naive persistence / random walk benchmark.
    Assumes future returns follow the empirical historical mean and standard deviation.
    """

    def __init__(self, model_version: str = "1.0.0") -> None:
        self._version = model_version
        self._drift: float = 0.0
        self._std: float = 0.02
        self._train_count: int = 0
        self._train_end: datetime | None = None

    @property
    def model_name(self) -> str:
        return "naive_drift_baseline"

    @property
    def model_version(self) -> str:
        return self._version

    @property
    def task_description(self) -> str:
        return "Empirical random walk with drift statistical baseline"

    def fit(
        self,
        features: pl.DataFrame | np.ndarray,
        labels: pl.Series | np.ndarray,
        *,
        train_end: datetime | None = None,
    ) -> None:
        """
        Fit baseline statistics strictly on the training set.
        """
        y = labels.to_numpy() if isinstance(labels, pl.Series) else np.asarray(labels)

        if len(y) == 0:
            raise ValueError("Training target labels are empty.")

        self._drift = float(np.mean(y))
        self._std = float(np.std(y, ddof=1)) if len(y) > 1 else 0.02
        if self._std < 1e-6:
            self._std = 0.01  # Safe floor
        self._train_count = len(y)
        self._train_end = train_end

    def predict(
        self,
        features: pl.DataFrame | np.ndarray,
        *,
        as_of: datetime,
        horizon: int,
        timeframe: Timeframe,
    ) -> dict[str, Any]:
        """
        Predict future return and uncertainty bounds.
        """
        # 80% confidence interval: z = 1.282; 90% confidence interval: z = 1.645
        z = 1.282
        lower = self._drift - z * self._std
        upper = self._drift + z * self._std

        # Class probabilities: P(R > 0.01), P(R < -0.01), P(|R| <= 0.01)
        # Using normal distribution N(drift, std)
        norm_dist = stats.norm(loc=self._drift, scale=self._std)
        p_up = float(1.0 - norm_dist.cdf(0.01))
        p_down = float(norm_dist.cdf(-0.01))
        p_flat = float(max(0.0, 1.0 - p_up - p_down))

        return {
            "point_estimate": round(self._drift, 5),
            "lower_bound": round(lower, 5),
            "upper_bound": round(upper, 5),
            "confidence": 0.80,
            "probabilities": {
                "up": round(p_up, 4),
                "flat": round(p_flat, 4),
                "down": round(p_down, 4),
            },
            "feature_importance": {"drift_historical": 1.0},
            "model_name": self.model_name,
            "model_version": self.model_version,
            "as_of": as_of,
        }

    def evaluate(
        self,
        features: pl.DataFrame | np.ndarray,
        labels: pl.Series | np.ndarray,
        *,
        eval_start: datetime | None = None,
        **kwargs: Any,
    ) -> dict[str, float]:
        """
        Compute out-of-sample metrics on validation set.
        """
        y_true = labels.to_numpy() if isinstance(labels, pl.Series) else np.asarray(labels)

        if len(y_true) == 0:
            return {"mae": 0.0, "rmse": 0.0, "win_rate": 0.50, "sharpe": 0.0}

        y_pred = np.full_like(y_true, fill_value=self._drift)
        mae = float(np.mean(np.abs(y_true - y_pred)))
        rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

        # Directional win rate: sign(predicted drift) == sign(actual return)
        pred_sign = np.sign(self._drift) if abs(self._drift) > 1e-4 else 1.0
        actual_sign = np.sign(y_true)
        correct = np.sum(pred_sign == actual_sign)
        win_rate = float(correct / len(y_true))

        # Sharpe ratio approximation
        mean_ret = float(np.mean(y_true))
        std_ret = float(np.std(y_true, ddof=1)) + 1e-6
        sharpe = float((mean_ret / std_ret) * np.sqrt(252 / 5))

        return {
            "mae": round(mae, 5),
            "rmse": round(rmse, 5),
            "win_rate": round(win_rate, 4),
            "sharpe": round(sharpe, 4),
        }

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.model_name}_{self.model_version}.json"
        data = {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "drift": self._drift,
            "std": self._std,
            "train_count": self._train_count,
            "train_end": self._train_end.isoformat() if self._train_end else None,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    def load(self, directory: Path) -> None:
        path = directory / f"{self.model_name}_{self.model_version}.json"
        if not path.exists():
            raise FileNotFoundError(f"Model file {path} not found.")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._drift = data["drift"]
        self._std = data["std"]
        self._train_count = data["train_count"]
        self._train_end = datetime.fromisoformat(data["train_end"]) if data["train_end"] else None

    def release(self) -> None:
        pass
