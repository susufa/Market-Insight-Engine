import asyncio
from datetime import datetime, UTC
from pathlib import Path
import pytest
import numpy as np
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
async def test_cold_restart_and_deterministic_inference():
    """Verify that restarting storage and reloading saved model artifacts preserves complete determinism."""
    # Phase 1: Pre-restart Session
    engine1 = CompositeStorageEngine(data_root=Path("data"))
    await engine1.initialise()
    
    symbol = "600519.SH"
    tf = Timeframe.D1
    start_cov1, end_cov1 = await engine1.sqlite.get_coverage(symbol, tf)
    assert start_cov1 is not None and end_cov1 is not None
    
    # Read bars
    df_bars1 = await engine1.read_bars(symbol, tf, start_cov1, end_cov1)
    bars1_count = len(df_bars1)
    assert bars1_count > 100
    
    # Convert to entities for model
    bars_list1 = df_to_bars(df_bars1, symbol, tf)
    
    # Train and forecast with LightGBM
    models_dir = Path("data/models/test_restart")
    registry1 = ModelRegistry(artifacts_dir=models_dir)
    
    summary1 = registry1.train_and_evaluate("lightgbm_quant_model", bars_list1, horizon=5)
    assert summary1.win_rate > 0
    
    pred1 = registry1.forecast(symbol, bars_list1, model_name="lightgbm_quant_model", horizon=5)
    assert pred1.point_estimate is not None
    
    # Persist model
    saved_path = registry1.save_model("lightgbm_quant_model", directory=models_dir)
    assert saved_path.exists()
    
    # Close session 1
    await engine1.close()
    del engine1
    del registry1
    
    # Phase 2: Cold Restart Session (New process state)
    engine2 = CompositeStorageEngine(data_root=Path("data"))
    await engine2.initialise()
    
    # Check SQLite coverage matches exactly
    start_cov2, end_cov2 = await engine2.sqlite.get_coverage(symbol, tf)
    assert start_cov2 == start_cov1
    assert end_cov2 == end_cov1
    
    df_bars2 = await engine2.read_bars(symbol, tf, start_cov2, end_cov2)
    assert len(df_bars2) == bars1_count
    
    bars_list2 = df_to_bars(df_bars2, symbol, tf)
    
    # New registry loading persisted model artifact
    registry2 = ModelRegistry(artifacts_dir=models_dir)
    registry2.load_model("lightgbm_quant_model", directory=models_dir)
    
    pred2 = registry2.forecast(symbol, bars_list2, model_name="lightgbm_quant_model", horizon=5)
    
    # Verification of Determinism across Cold Restart
    assert np.isclose(pred2.point_estimate, pred1.point_estimate, atol=1e-6), (
        f"Point estimate mismatch after cold restart: {pred2.point_estimate} vs {pred1.point_estimate}"
    )
    assert np.isclose(pred2.lower_bound, pred1.lower_bound, atol=1e-6)
    assert np.isclose(pred2.upper_bound, pred1.upper_bound, atol=1e-6)
    assert pred2.probabilities == pred1.probabilities
    assert pred2.data_origin == DataOrigin.REAL_PROVIDER
    assert not pred2.is_synthetic
    
    await engine2.close()
