"""
models/entities.py
~~~~~~~~~~~~~~~~~~
Standard data models and schemas for the prediction framework.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum

from pydantic import BaseModel, Field, model_validator

from core.entities import DataOrigin


class PredictionHorizon(int, Enum):
    """Supported prediction forecast horizons in trading days."""

    D1 = 1
    D3 = 3
    D5 = 5
    D10 = 10
    D20 = 20


class PredictionTaskType(StrEnum):
    """Prediction task category."""

    RETURN_REGRESSION = "return_regression"
    TREND_CLASSIFICATION = "trend_classification"


class PredictionResult(BaseModel):
    """
    Standard structured prediction output across all model types.
    Strictly forbids naked single-point signals; requires confidence,
    uncertainty bounds, probability distribution, and explicit disclaimer.
    """

    symbol: str = Field(..., description="Target security symbol, e.g. '600519.SH'")
    as_of: datetime = Field(..., description="Cutoff timestamp (strict point-in-time)")
    horizon: int = Field(default=5, description="Forecast horizon in trading days")
    timeframe: str = Field(default="1d", description="Bar timeframe, e.g. '1d'")
    model_name: str = Field(..., description="Name of predictive model")
    model_version: str = Field(..., description="Semantic version of model")
    point_estimate: float = Field(
        ..., description="Expected return over horizon, e.g. 0.024 (+2.4%)"
    )
    lower_bound: float = Field(..., description="Lower uncertainty bound (10th percentile)")
    upper_bound: float = Field(..., description="Upper uncertainty bound (90th percentile)")
    confidence: float = Field(
        default=0.80, description="Confidence interval level, e.g. 0.80 for 80%"
    )
    probabilities: dict[str, float] = Field(
        default_factory=dict,
        description="Probability across states, e.g. {'up': 0.58, 'flat': 0.14, 'down': 0.28}",
    )
    feature_importance: dict[str, float] = Field(
        default_factory=dict,
        description="Top contributing feature importances for interpretability",
    )
    train_date_range: tuple[str, str] = Field(
        default=("", ""), description="Date range of training samples used"
    )
    test_evaluation: dict[str, float] = Field(
        default_factory=dict,
        description="Out-of-sample validation metrics (win_rate, sharpe, max_drawdown, mae)",
    )
    disclaimer: str = Field(
        default="学术研究与量化回测参考，不构成任何投资建议或确定性交易依据",
        description="Mandatory compliance disclaimer",
    )
    data_origin: DataOrigin = Field(
        default=DataOrigin.UNKNOWN,
        description="Origin of input market data (real_provider, synthetic_test, etc.)",
    )
    is_synthetic: bool = Field(
        default=False,
        description="Explicit flag indicating whether prediction is based on synthetic/demo data",
    )
    data_source: str = Field(
        default="storage",
        description="Underlying data source name or interface",
    )
    warning_message: str | None = Field(
        default=None,
        description="Operational warning, insufficient data notice, or demo disclaimer",
    )

    @model_validator(mode="after")
    def validate_bounds_and_probs(self) -> PredictionResult:
        if self.lower_bound > self.point_estimate:
            msg = f"lower_bound ({self.lower_bound}) must be <= point ({self.point_estimate})"
            raise ValueError(msg)
        if self.upper_bound < self.point_estimate:
            msg = f"upper_bound ({self.upper_bound}) must be >= point ({self.point_estimate})"
            raise ValueError(msg)
        if self.probabilities:
            prob_sum = sum(self.probabilities.values())
            if not (0.95 <= prob_sum <= 1.05):
                msg = f"Probabilities must sum to ~1.0, got sum={prob_sum:.4f}"
                raise ValueError(msg)
        return self


class ModelEvaluationSummary(BaseModel):
    """Out-of-sample walk-forward validation evaluation report."""

    model_name: str
    model_version: str
    sample_count: int
    fold_count: int
    win_rate: float = Field(..., description="Directional accuracy / win rate, e.g. 0.562")
    sharpe_ratio: float = Field(..., description="Annualized strategy Sharpe ratio")
    max_drawdown: float = Field(..., description="Maximum drawdown during out-of-sample period")
    mae: float = Field(..., description="Mean Absolute Error on return regression")
    rmse: float = Field(..., description="Root Mean Squared Error")
    baseline_win_rate: float = Field(default=0.50, description="Baseline model win rate")
    baseline_sharpe: float = Field(default=0.80, description="Baseline model Sharpe ratio")
    outperformed_baseline: bool = Field(
        default=True, description="Whether model passed the admission gate"
    )
    data_origin: DataOrigin = Field(
        default=DataOrigin.UNKNOWN, description="Origin of evaluation dataset"
    )
    is_synthetic: bool = Field(
        default=False,
        description="Explicit flag indicating whether evaluation used synthetic/demo data",
    )
    data_source: str = Field(
        default="storage", description="Underlying evaluation data source name"
    )
    warning_message: str | None = Field(
        default=None,
        description="Operational warning, insufficient data notice, or demo disclaimer",
    )
    evaluation_time: datetime = Field(default_factory=datetime.utcnow)
