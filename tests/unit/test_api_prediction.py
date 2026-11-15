"""
tests/unit/test_api_prediction.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the FastAPI prediction and walk-forward verification endpoints.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_api_list_models() -> None:
    resp = client.get("/api/v1/prediction/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    assert data["count"] >= 3
    models = data["models"]
    model_names = [m["model_name"] for m in models]
    assert "naive_drift_baseline" in model_names
    assert "lightgbm_quant_model" in model_names


def test_api_forecast_structure_and_disclaimer() -> None:
    endpoint = (
        "/api/v1/prediction/forecast?symbol=600519.SH&horizon=5&model_name=lightgbm_quant_model"
    )
    resp = client.get(endpoint)
    assert resp.status_code == 200
    data = resp.json()

    assert data["symbol"] == "600519.SH"
    assert data["horizon"] == 5
    assert "point_estimate" in data
    assert "lower_bound" in data
    assert "upper_bound" in data
    assert data["lower_bound"] <= data["point_estimate"] <= data["upper_bound"]

    # Must include probabilities
    probs = data["probabilities"]
    assert "up" in probs and "down" in probs and "flat" in probs

    # Must include mandatory compliance disclaimer
    assert "disclaimer" in data
    assert "学术研究与量化回测参考" in data["disclaimer"]
    assert "不构成任何投资建议" in data["disclaimer"]


def test_api_walk_forward_report() -> None:
    resp = client.get("/api/v1/prediction/walk-forward-report?symbol=600519.SH&horizon=5")
    assert resp.status_code == 200
    data = resp.json()

    assert data["model_name"] == "lightgbm_quant_model"
    assert data["fold_count"] >= 1
    assert "win_rate" in data
    assert "sharpe_ratio" in data
    assert "baseline_win_rate" in data
    assert "outperformed_baseline" in data


def test_api_train_trigger() -> None:
    resp = client.post(
        "/api/v1/prediction/train",
        json={"symbol": "600519.SH", "model_name": "lightgbm_quant_model", "horizon": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "summary" in data
    assert data["summary"]["model_name"] == "lightgbm_quant_model"
