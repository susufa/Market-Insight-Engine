"""
tests/unit/test_api_system.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the FastAPI application and system endpoints.

Verifies:
- GET /                     → Root status check
- GET /api/v1/system/health → Liveness probe
- GET /api/v1/system/info   → Runtime configuration metadata
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Market Insight Engine"
    assert data["status"] == "ok"
    assert data["version"] == "0.10.0"


def test_system_health() -> None:
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.10.0"
    assert "timestamp" in data


def test_system_info() -> None:
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "0.10.0"
    assert data["env"] in ("development", "test", "production")
    assert "python_version" in data
    assert "platform" in data
    assert "data_root" in data
    assert data["gpu_enabled"] is False


def test_default_listen_host_is_loopback() -> None:
    """Security invariant: the API must default strictly to 127.0.0.1 (local loopback)."""
    from config.settings import get_settings

    settings = get_settings()
    assert settings.host == "127.0.0.1", f"Expected default host 127.0.0.1, got {settings.host}"
    assert settings.port == 8000


def test_cors_origins_are_local_only() -> None:
    """Security invariant: CORS origins must only permit localhost/127.0.0.1."""
    from starlette.middleware.cors import CORSMiddleware

    cors_middlewares = [m for m in app.user_middleware if issubclass(m.cls, CORSMiddleware)]
    assert len(cors_middlewares) == 1
    allowed_origins = cors_middlewares[0].kwargs.get("allow_origins", [])
    for origin in allowed_origins:
        assert "localhost" in origin or "127.0.0.1" in origin, f"Non-local CORS origin: {origin}"
