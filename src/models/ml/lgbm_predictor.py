"""
models/ml/lgbm_predictor.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Gradient Boosted Decision Trees (LightGBM) quantitative predictor.

Features:
- Point estimate for expected N-day forward return.
- Uncertainty bands and empirical quantile bounds.
- Categorical state probability distribution (Up / Flat / Down).
- Tree feature importance attribution.
- Out-of-sample Sharpe and directional accuracy evaluation.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import polars as pl
from scipy import stats

from core.entities import Timeframe
from core.interfaces.predictor import BasePredictor


class LightGBMPredictor(BasePredictor):
    """
    LightGBM Gradient Boosted Decision Tree model for financial time series.
    """

    def __init__(
        self,
        model_version: str = "1.0.0",
        n_estimators: int = 100,
        learning_rate: float = 0.03,
        max_depth: int = 4,
        num_leaves: int = 15,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        random_state: int = 42,
    ) -> None:
        self._version = model_version
        self._params: dict[str, Any] = {
            "n_estimators": n_estimators,
            "learning_rate": learning_rate,
            "max_depth": max_depth,
            "num_leaves": num_leaves,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "random_state": random_state,
            "verbose": -1,
            "n_jobs": 2,
        }
        self._model = lgb.LGBMRegressor(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            num_leaves=num_leaves,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            random_state=random_state,
            verbose=-1,
            n_jobs=2,
        )
        self._train_end: datetime | None = None
        self._feature_names: list[str] = []
        self._residual_std: float = 0.02
        self._fitted: bool = False

    @property
    def model_name(self) -> str:
        return "lightgbm_quant_model"

    @property
    def model_version(self) -> str:
        return self._version

    @property
    def task_description(self) -> str:
        return "Gradient Boosted Decision Trees for multi-day return and trend probability"

    def fit(
        self,
        features: pl.DataFrame | np.ndarray,
        labels: pl.Series | np.ndarray,
        *,
        train_end: datetime | None = None,
    ) -> None:
        if isinstance(features, pl.DataFrame):
            self._feature_names = features.columns
            X = features.to_numpy()
        else:
            X = np.asarray(features)
            self._feature_names = [f"f_{i}" for i in range(X.shape[1])]

        y = labels.to_numpy() if isinstance(labels, pl.Series) else np.asarray(labels)

        if len(y) == 0:
            raise ValueError("Training targets are empty.")

        self._model.fit(X, y)
        self._booster = self._model.booster_
        preds = self._model.predict(X)
        residuals = y - preds

        # Out-of-Fold (OOF) CV residual estimation to prevent in-sample underestimation
        if len(y) >= 40:
            oof_residuals: list[float] = []
            fold_size = max(10, len(y) // 4)
            n_folds = min(4, len(y) // fold_size)
            for fold in range(1, n_folds):
                train_slice = slice(0, fold * fold_size)
                end_idx = (fold + 1) * fold_size if fold < n_folds - 1 else len(y)
                val_slice = slice(fold * fold_size, end_idx)
                if val_slice.stop > val_slice.start and train_slice.stop > train_slice.start:
                    fold_model = lgb.LGBMRegressor(**self._params)
                    fold_model.fit(X[train_slice], y[train_slice])
                    val_preds = fold_model.predict(X[val_slice])
                    oof_residuals.extend((y[val_slice] - val_preds).tolist())
            if len(oof_residuals) >= 10:
                self._residual_std = float(np.std(oof_residuals, ddof=1))
            else:
                self._residual_std = float(np.std(residuals, ddof=1)) * 1.25
        else:
            self._residual_std = float(np.std(residuals, ddof=1)) * 1.25

        if self._residual_std < 1e-4:
            self._residual_std = 0.015

        self._train_end = train_end
        self._fitted = True

    def predict(
        self,
        features: pl.DataFrame | np.ndarray,
        *,
        as_of: datetime,
        horizon: int,
        timeframe: Timeframe,
    ) -> dict[str, Any]:
        if not self._fitted:
            raise RuntimeError("Model has not been fitted yet.")

        X = features.to_numpy() if isinstance(features, pl.DataFrame) else np.asarray(features)

        if X.ndim == 1:
            X = X.reshape(1, -1)

        if hasattr(self, "_booster") and self._booster is not None:
            y_preds = self._booster.predict(X)
        else:
            y_preds = self._model.predict(X)
        y_pred = float(y_preds[-1])

        # 80% confidence interval: z = 1.282; 90% confidence interval: z = 1.645
        z = 1.282
        lower = y_pred - z * self._residual_std
        upper = y_pred + z * self._residual_std

        # State probabilities based on residual calibration
        norm_dist = stats.norm(loc=y_pred, scale=self._residual_std)
        p_up = float(1.0 - norm_dist.cdf(0.01))
        p_down = float(norm_dist.cdf(-0.01))
        p_flat = float(max(0.0, 1.0 - p_up - p_down))

        # Normalized feature importance
        importances = self._model.feature_importances_
        total_imp = float(np.sum(importances)) + 1e-9
        feat_imp: dict[str, float] = {}
        for name, imp in zip(self._feature_names, importances, strict=False):
            feat_imp[name] = round(float(imp / total_imp), 4)

        # Sort feature importances descending
        sorted_imp = dict(sorted(feat_imp.items(), key=lambda kv: kv[1], reverse=True)[:5])

        return {
            "point_estimate": round(y_pred, 5),
            "lower_bound": round(lower, 5),
            "upper_bound": round(upper, 5),
            "confidence": 0.80,
            "probabilities": {
                "up": round(p_up, 4),
                "flat": round(p_flat, 4),
                "down": round(p_down, 4),
            },
            "feature_importance": sorted_imp,
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
        long_only: bool = True,
        friction_bps: float = 25.0,
        horizon: int = 5,
    ) -> dict[str, float]:
        if not self._fitted:
            raise RuntimeError("Model has not been fitted yet.")

        X = features.to_numpy() if isinstance(features, pl.DataFrame) else np.asarray(features)

        y_true = labels.to_numpy() if isinstance(labels, pl.Series) else np.asarray(labels)

        if len(y_true) == 0:
            return {"mae": 0.0, "rmse": 0.0, "win_rate": 0.50, "sharpe": 0.0, "max_drawdown": 0.0}

        y_arr = np.asarray(self._model.predict(X), dtype=float)
        mae = float(np.mean(np.abs(y_true - y_arr)))
        rmse = float(np.sqrt(np.mean((y_true - y_arr) ** 2)))

        # Directional win rate (accuracy)
        pred_sign = np.sign(y_arr)
        actual_sign = np.sign(y_true)
        correct = np.sum(pred_sign == actual_sign)
        win_rate = float(correct / len(y_true))

        # Realistic execution: A-share long-only constraint and 25 bps transaction friction
        positions = np.where(y_arr > 0.0, 1.0, 0.0) if long_only else pred_sign

        # Deduct transaction friction on position changes
        turnover = np.abs(np.diff(positions, prepend=0.0))
        friction_cost = turnover * (friction_bps / 10000.0)
        net_ret = positions * y_true - friction_cost

        # Sample at non-overlapping stride = horizon to avoid compounding correlation
        stride = max(1, horizon)
        non_overlap_ret = net_ret[::stride]
        if len(non_overlap_ret) < 2:
            non_overlap_ret = net_ret

        mean_ret = float(np.mean(non_overlap_ret))
        std_ret = float(np.std(non_overlap_ret, ddof=1)) + 1e-6
        periods_per_year = 252.0 / float(stride)
        sharpe = float((mean_ret / std_ret) * np.sqrt(periods_per_year))

        # Max drawdown calculation on equity curve
        cum_ret = np.cumprod(1.0 + np.clip(non_overlap_ret, -0.99, 10.0))
        running_max = np.maximum.accumulate(cum_ret)
        drawdowns = (running_max - cum_ret) / np.maximum(running_max, 1e-6)
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        return {
            "mae": round(mae, 5),
            "rmse": round(rmse, 5),
            "win_rate": round(win_rate, 4),
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
        }

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        model_path = directory / f"{self.model_name}_{self.model_version}.txt"
        meta_path = directory / f"{self.model_name}_{self.model_version}_meta.json"

        # Save LightGBM booster
        self._model.booster_.save_model(str(model_path))

        meta = {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "params": self._params,
            "residual_std": self._residual_std,
            "feature_names": self._feature_names,
            "fitted": self._fitted,
            "train_end": self._train_end.isoformat() if self._train_end else None,
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return model_path

    def load(self, directory: Path) -> None:
        model_path = directory / f"{self.model_name}_{self.model_version}.txt"
        meta_path = directory / f"{self.model_name}_{self.model_version}_meta.json"

        if not model_path.exists() or not meta_path.exists():
            raise FileNotFoundError(f"Model artifacts not found in {directory}.")

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        self._params = meta["params"]
        self._residual_std = meta["residual_std"]
        self._feature_names = meta["feature_names"]
        self._fitted = meta["fitted"]
        self._train_end = datetime.fromisoformat(meta["train_end"]) if meta["train_end"] else None

        booster = lgb.Booster(model_file=str(model_path))
        self._booster = booster
        self._model = lgb.LGBMRegressor(**self._params)
        self._model._Booster = booster
        self._model.fitted_ = True
        self._model.n_features_in_ = len(self._feature_names)

    def release(self) -> None:
        pass
