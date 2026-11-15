"""
src/api/v1/prediction.py
~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI endpoints for the Predictive Framework & Verification engine (Phase 5).
- GET  /api/v1/prediction/models               : Catalog of available models
- GET  /api/v1/prediction/forecast             : Point-in-time forward predictions
- GET  /api/v1/prediction/walk-forward-report  : Walk-forward evaluation report
- POST /api/v1/prediction/train                : Trigger model training on bars
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.v1.market import get_storage
from core.entities import DataOrigin, Market, MarketBar, Timeframe
from models.entities import ModelEvaluationSummary, PredictionResult
from models.registry import ModelRegistry
from storage.composite_engine import CompositeStorageEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prediction", tags=["Predictive Framework & Verification"])

# Global model registry instance
_registry = ModelRegistry()


# =========================================================================== #
# Request & Response Schemas
# =========================================================================== #


class TrainRequest(BaseModel):
    symbol: str = Field(default="600519.SH", description="Security symbol to train on")
    model_name: str = Field(default="lightgbm_quant_model", description="Model identifier")
    horizon: int = Field(default=5, description="Prediction horizon in trading days")
    allow_synthetic: bool = Field(default=False, description="Allow offline synthetic mock data")


# =========================================================================== #
# Helper to fetch bars from storage with synthetic fallback
# =========================================================================== #


async def _fetch_bars_for_symbol(
    engine: CompositeStorageEngine,
    symbol: str,
    limit: int = 1500,
    allow_synthetic: bool = False,
) -> list[MarketBar]:
    """Retrieve raw historical daily bars for model fitting or inference."""
    try:
        now = datetime.now(tz=UTC)
        range_start = now - timedelta(days=365 * 10)
        raw_df = await engine.read_bars(
            symbol=symbol,
            timeframe=Timeframe.D1,
            start=range_start,
            end=now,
        )
        if raw_df is not None and not raw_df.is_empty():
            if raw_df.height < 50:
                msg = f"Insufficient bars for '{symbol}' (need >= 50, found {raw_df.height})."
                raise HTTPException(status_code=422, detail=msg)
            raw_bars = [
                MarketBar(
                    symbol=symbol,
                    timeframe=Timeframe.D1,
                    ts=r["ts"],
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    volume=r["volume"],
                    amount=r["amount"],
                    source_id=r.get("source_id", "local_store"),
                    data_origin=DataOrigin(r.get("data_origin", "real_provider")),
                    source_interface=r.get("source_interface", "local_store"),
                    checksum=r.get("checksum", ""),
                )
                for r in raw_df.to_dicts()
            ]
            return sorted(raw_bars, key=lambda b: b.ts)[-limit:]
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Could not read bars from storage for %s: %s", symbol, exc)

    if not allow_synthetic:
        err_msg = (
            f"No real historical bar data found in storage for symbol '{symbol}'. "
            "Ingest real market data or pass allow_synthetic=true for offline demo mode."
        )
        raise HTTPException(status_code=404, detail=err_msg)

    # Explicit offline synthetic generator (only reachable when allow_synthetic=True)
    base_price = 1500.0 if "600519" in symbol else 100.0
    now = datetime.now(tz=UTC)
    bars_synth: list[MarketBar] = []
    price = base_price

    for i in range(700):
        dt = now - timedelta(days=700 - i)
        if dt.weekday() in (5, 6):
            continue
        drift = 0.0003 + 0.012 * ((i % 17) - 8) / 8.0
        price = max(10.0, price * (1.0 + drift))
        high = price * 1.015
        low = price * 0.985
        open_p = price * 0.998
        vol = 2000000.0 + (i % 10) * 150000.0

        bars_synth.append(
            MarketBar(
                symbol=symbol,
                ts=dt,
                timeframe=Timeframe.D1,
                open=round(open_p, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(price, 2),
                volume=round(vol, 0),
                amount=round(vol * price, 2),
                market=Market.CN_A,
                source_id="mock_synth",
                source_interface="offline_synthetic_generator",
                data_origin=DataOrigin.SYNTHETIC_TEST,
                checksum="mock_synth_checksum",
            )
        )
    return bars_synth


# =========================================================================== #
# API Endpoints
# =========================================================================== #


@router.get("/models")
async def list_models() -> dict[str, Any]:
    """List all registered statistical baseline and ML models."""
    return {
        "count": len(_registry.list_models()),
        "models": _registry.list_models(),
    }


@router.get("/forecast", response_model=PredictionResult)
async def get_forecast(
    symbol: str = Query(default="600519.SH", description="Security symbol"),
    model_name: str = Query(default="lightgbm_quant_model", description="Model name"),
    horizon: int = Query(default=5, ge=1, le=60, description="Forecast horizon in days"),
    allow_synthetic: bool = Query(default=False, description="Allow offline synthetic fallback"),
) -> PredictionResult:
    """
    Generate point-in-time probabilistic forecast for `symbol` over `horizon` days.
    Includes expected return, 80% confidence interval, multi-class probabilities,
    feature importance, and mandatory compliance disclaimer.
    """
    engine = await get_storage()
    bars = await _fetch_bars_for_symbol(engine, symbol, allow_synthetic=allow_synthetic)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No bar data available for symbol '{symbol}'.")

    try:
        return _registry.forecast(
            symbol=symbol,
            bars=bars,
            model_name=model_name,
            horizon=horizon,
            timeframe=Timeframe.D1,
        )
    except Exception as exc:
        logger.error("Forecast failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction error: {exc}") from exc


@router.get("/walk-forward-report", response_model=ModelEvaluationSummary)
async def get_walk_forward_report(
    symbol: str = Query(default="600519.SH", description="Security symbol"),
    model_name: str = Query(default="lightgbm_quant_model", description="Model name"),
    horizon: int = Query(default=5, ge=1, le=20, description="Forecast horizon"),
    allow_synthetic: bool = Query(default=False, description="Allow offline synthetic fallback"),
) -> ModelEvaluationSummary:
    """
    Execute walk-forward out-of-sample cross validation for the given model,
    benchmarking win rate, Sharpe ratio, and drawdown against naive baseline.
    """
    engine = await get_storage()
    bars = await _fetch_bars_for_symbol(engine, symbol, allow_synthetic=allow_synthetic)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No data available for symbol '{symbol}'.")

    try:
        return _registry.train_and_evaluate(
            model_name=model_name,
            bars=bars,
            horizon=horizon,
        )
    except Exception as exc:
        logger.error("Walk-forward evaluation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation error: {exc}") from exc


@router.post("/train")
async def trigger_training(req: TrainRequest) -> dict[str, Any]:
    """Train or retrain a model on historical bars with walk-forward validation."""
    engine = await get_storage()
    bars = await _fetch_bars_for_symbol(engine, req.symbol, allow_synthetic=req.allow_synthetic)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No bars for {req.symbol}")

    summary = _registry.train_and_evaluate(
        model_name=req.model_name,
        bars=bars,
        horizon=req.horizon,
    )
    return {
        "status": "success",
        "symbol": req.symbol,
        "model_name": req.model_name,
        "summary": summary.model_dump(),
    }
