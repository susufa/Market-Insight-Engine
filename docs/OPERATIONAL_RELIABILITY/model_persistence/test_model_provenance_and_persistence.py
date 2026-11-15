from datetime import datetime, UTC
from pathlib import Path
import json
import pytest
import polars as pl

from core.entities import Timeframe, DataOrigin, MarketBar
from storage.composite_engine import CompositeStorageEngine
from models.registry import ModelRegistry

def df_to_bars(df: pl.DataFrame, symbol: str, tf: Timeframe) -> list[MarketBar]:
    return [
        MarketBar(
            symbol=symbol,
            timeframe=tf,
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
        for r in df.to_dicts()
    ]

@pytest.mark.asyncio
async def test_all_models_persistence_and_provenance():
    """Verify that Naive, Ridge, and LightGBM models persist metadata tied to real dataset provenance."""
    engine = CompositeStorageEngine(data_root=Path("data"))
    await engine.initialise()
    
    symbol = "600519.SH"
    tf = Timeframe.D1
    s, e = await engine.sqlite.get_coverage(symbol, tf)
    assert s is not None and e is not None
    
    df_raw = await engine.read_bars(symbol, tf, s, e)
    bars = df_to_bars(df_raw, symbol, tf)
    assert len(bars) > 50
    
    models_dir = Path("data/models/provenance_audit")
    registry = ModelRegistry(artifacts_dir=models_dir)
    
    # 1. Naive Baseline
    summary_naive = registry.train_and_evaluate("naive_drift_baseline", bars, horizon=5)
    pred_naive = registry.forecast(symbol, bars, model_name="naive_drift_baseline", horizon=5)
    saved_naive = registry.save_model("naive_drift_baseline", directory=models_dir)
    assert saved_naive.exists()
    assert pred_naive.data_origin == DataOrigin.REAL_PROVIDER
    assert not pred_naive.is_synthetic
    
    # 2. Ridge Baseline
    summary_ridge = registry.train_and_evaluate("ridge_linear_baseline", bars, horizon=5)
    pred_ridge = registry.forecast(symbol, bars, model_name="ridge_linear_baseline", horizon=5)
    saved_ridge = registry.save_model("ridge_linear_baseline", directory=models_dir)
    assert saved_ridge.exists()
    assert pred_ridge.data_origin == DataOrigin.REAL_PROVIDER
    assert not pred_ridge.is_synthetic
    
    # 3. LightGBM Quant Model
    summary_lgbm = registry.train_and_evaluate("lightgbm_quant_model", bars, horizon=5)
    pred_lgbm = registry.forecast(symbol, bars, model_name="lightgbm_quant_model", horizon=5)
    saved_lgbm = registry.save_model("lightgbm_quant_model", directory=models_dir)
    assert saved_lgbm.exists()
    assert pred_lgbm.data_origin == DataOrigin.REAL_PROVIDER
    assert not pred_lgbm.is_synthetic
    
    # Verify metadata JSON fields
    meta_path = models_dir / "lightgbm_quant_model_1.0.0_meta.json"
    assert meta_path.exists()
    with open(meta_path, encoding="utf-8") as f:
        meta_data = json.load(f)
    assert meta_data["model_name"] == "lightgbm_quant_model"
    assert meta_data["model_version"] == "1.0.0"
    assert meta_data["fitted"] is True
    assert len(meta_data["feature_names"]) > 5
    assert meta_data["train_end"] is not None
    
    # Verify reload
    reg_fresh = ModelRegistry(artifacts_dir=models_dir)
    reg_fresh.load_model("naive_drift_baseline", directory=models_dir)
    reg_fresh.load_model("ridge_linear_baseline", directory=models_dir)
    reg_fresh.load_model("lightgbm_quant_model", directory=models_dir)
    
    assert getattr(reg_fresh.get_model("lightgbm_quant_model"), "_fitted", False) is True
    
    await engine.close()
