"""
tests/integration/test_api_acquisition.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Integration tests for data acquisition REST endpoints (/api/v1/acquisition/...).
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_api_providers_health(client):
    """Verify GET /api/v1/acquisition/providers/health."""
    response = client.get("/api/v1/acquisition/providers/health")
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "akshare" in data["providers"]


def test_api_create_and_query_task_lifecycle(client):
    """Verify task creation, listing, detail query, and cancellation."""
    # 1. Create Task
    payload = {
        "symbols": ["600519.SH", "000858.SZ"],
        "timeframe": "1d",
        "start_date": "2023-01-01",
        "end_date": "2023-01-10",
        "provider_preference": "auto",
        "force_refresh": False,
    }
    create_resp = client.post("/api/v1/acquisition/tasks", json=payload)
    assert create_resp.status_code == 202
    created = create_resp.json()
    task_id = created["task_id"]
    assert task_id.startswith("acq_")
    assert created["symbols_count"] == 2

    # 2. Query Detail
    detail_resp = client.get(f"/api/v1/acquisition/tasks/{task_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["task_id"] == task_id
    assert detail["total_symbols"] == 2
    assert "items" in detail
    assert len(detail["items"]) == 2

    # 3. List Tasks
    list_resp = client.get("/api/v1/acquisition/tasks?limit=10")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert "tasks" in list_data
    found = any(t["task_id"] == task_id for t in list_data["tasks"])
    assert found is True

    # 4. Cancel Task
    cancel_resp = client.post(f"/api/v1/acquisition/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == 200
    cancel_data = cancel_resp.json()
    assert cancel_data["status"] == "CANCELLED"

    # 5. Resume Task
    resume_resp = client.post(f"/api/v1/acquisition/tasks/{task_id}/resume")
    assert resume_resp.status_code == 200
    resume_data = resume_resp.json()
    assert "resumed" in resume_data


def test_api_cleanup_zombies(client):
    """Verify POST /api/v1/acquisition/tasks/cleanup-zombies."""
    response = client.post("/api/v1/acquisition/tasks/cleanup-zombies")
    assert response.status_code == 200
    data = response.json()
    assert "cleaned_zombie_tasks_count" in data
    assert isinstance(data["cleaned_zombie_tasks_count"], int)


def test_api_task_not_found(client):
    """Verify 404 on invalid task ID."""
    response = client.get("/api/v1/acquisition/tasks/non_existent_task_id")
    assert response.status_code == 404
