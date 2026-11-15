"""
core/interfaces/predictor.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Abstract contract for all predictive model implementations.

Design rules
------------
- Models must NEVER read future data; the `predict()` call receives only
  data up to `as_of` (exclusive of anything after it).
- Output must include uncertainty / confidence information; point
  forecasts alone are forbidden.
- Every model is independently loadable, saveable, and evaluatable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from core.entities import Timeframe


class PredictionResult:
    """
    Base class for model outputs.

    Concrete models define their own result dataclass inheriting from this.
    At minimum they must expose:
    - `symbol`     : str
    - `as_of`      : datetime  (last timestamp seen by the model)
    - `horizon`    : int       (forecast horizon in bars)
    - `timeframe`  : Timeframe
    - `model_name` : str
    - `model_version` : str
    """


class BasePredictor(ABC):
    """
    Port definition for all predictive models.

    Lifecycle:  __init__ → fit() → predict() / evaluate()
                        → save() / load()
    """

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Stable machine-readable identifier, e.g. 'lgbm_return_5d'."""

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Semantic version string, e.g. '1.0.0'."""

    @property
    @abstractmethod
    def task_description(self) -> str:
        """Human-readable description of the prediction task."""

    # ------------------------------------------------------------------ #
    # Training
    # ------------------------------------------------------------------ #

    @abstractmethod
    def fit(
        self,
        features: pl.DataFrame | np.ndarray[Any, Any],
        labels: pl.Series | np.ndarray[Any, Any],
        *,
        train_end: datetime | None = None,
    ) -> None:
        """
        Train the model on `features` / `labels`.

        Parameters
        ----------
        features  : Feature matrix (DataFrame or numpy ndarray).
                    Must NOT contain any rows with timestamps > `train_end`.
        labels    : Target vector aligned to `features`.
        train_end : Explicit training cutoff (enforced by anti-leakage guard).
        """

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #

    @abstractmethod
    def predict(
        self,
        features: pl.DataFrame | np.ndarray[Any, Any],
        *,
        as_of: datetime,
        horizon: int,
        timeframe: Timeframe,
    ) -> dict[str, Any]:
        """
        Generate predictions for the given feature snapshot.

        Parameters
        ----------
        features  : Most-recent feature window (no future rows).
        as_of     : Point-in-time cutoff (last known timestamp).
        horizon   : Forecast horizon in bars.
        timeframe : Bar frequency for the forecast horizon.

        Returns
        -------
        Dict containing at minimum:
          - 'point_estimate' : float
          - 'lower_bound'    : float
          - 'upper_bound'    : float
          - 'confidence'     : float  (0.0 – 1.0)
          - 'model_name'     : str
          - 'model_version'  : str
          - 'as_of'          : datetime
        """

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #

    @abstractmethod
    def evaluate(
        self,
        features: pl.DataFrame | np.ndarray[Any, Any],
        labels: pl.Series | np.ndarray[Any, Any],
        *,
        eval_start: datetime | None = None,
    ) -> dict[str, float]:
        """
        Compute evaluation metrics on out-of-sample data.

        Returns a dict of metric_name → value, e.g.:
          {'mae': 0.012, 'rmse': 0.018, 'hit_rate': 0.54}
        """

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #

    @abstractmethod
    def save(self, directory: Path) -> Path:
        """
        Persist model weights and metadata to `directory`.

        Returns the path to the saved artefact (file or sub-directory).
        """

    @abstractmethod
    def load(self, directory: Path) -> None:
        """Load model weights and metadata from `directory`."""

    # ------------------------------------------------------------------ #
    # Resource management
    # ------------------------------------------------------------------ #

    @abstractmethod
    def release(self) -> None:
        """Release any held GPU / memory resources."""
