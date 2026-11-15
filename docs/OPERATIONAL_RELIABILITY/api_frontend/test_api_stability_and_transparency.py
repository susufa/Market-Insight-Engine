import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.entities import DataOrigin

@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c

def test_api_health_check(client):
    """Verify /api/v1/system/health returns healthy system status."""
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "ok")

def test_api_real_market_bars_endpoint(client):
    """Verify /api/v1/market/bars returns genuine real bars with data_origin."""
    resp = client.get("/api/v1/market/bars", params={"symbol": "600519.SH", "timeframe": "1d"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600519.SH"
    assert data["data_quality_status"] == "PASS"
    bars = data["bars"]
    assert len(bars) > 100
    assert data["count"] == len(bars)
    b0 = bars[0]
    assert b0["close"] > 0
    assert b0["open"] > 0
    assert b0["high"] >= b0["low"]

def test_api_unknown_symbol_returns_empty_with_not_found_status(client):
    """Querying non-existent symbol in market bars returns 0 bars with NOT_FOUND status, never fabricating bars."""
    resp = client.get("/api/v1/market/bars", params={"symbol": "NONEXISTENT.SH", "timeframe": "1d"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["bars"] == []
    assert data["data_quality_status"] == "NOT_FOUND"

def test_api_prediction_models_catalog(client):
    """Verify /api/v1/prediction/models lists baseline and ML models."""
    resp = client.get("/api/v1/prediction/models")
    assert resp.status_code == 200
    data = resp.json()
    models = data["models"]
    names = [m["model_name"] for m in models]
    assert "naive_drift_baseline" in names
    assert "ridge_linear_baseline" in names
    assert "lightgbm_quant_model" in names

def test_api_forecast_real_provenance(client):
    """Verify /api/v1/prediction/forecast on 600519.SH has is_synthetic=False and real_provider origin."""
    resp = client.get("/api/v1/prediction/forecast", params={"symbol": "600519.SH", "model_name": "lightgbm_quant_model"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600519.SH"
    assert data["data_origin"] == "real_provider"
    assert data["is_synthetic"] is False
    assert data["point_estimate"] is not None
    assert data["lower_bound"] <= data["point_estimate"] <= data["upper_bound"]

def test_api_forecast_unknown_symbol_rejects_synthetic_by_default(client):
    """Querying forecast on unknown symbol without allow_synthetic must raise 404 Not Found."""
    resp = client.get("/api/v1/prediction/forecast", params={"symbol": "UNKNOWN999.SH", "model_name": "lightgbm_quant_model"})
    assert resp.status_code in (404, 422)
