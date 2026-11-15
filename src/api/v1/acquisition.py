"""
src/api/v1/acquisition.py
~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI endpoints for data acquisition task orchestration and monitoring:
- Trigger asynchronous acquisition tasks
- Query task progress and detailed item states
- Cancel or resume tasks
- Sweep zombie tasks
- Provider health diagnostics
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from config import get_settings
from src.acquisition.providers.akshare_provider import AKShareProvider
from src.acquisition.providers.mock_provider import MockProvider
from src.acquisition.registry import ProviderRegistry
from src.acquisition.service import AcquisitionService
from src.acquisition.task_manager import AcquisitionTaskManager
from src.api.v1.market import get_storage
from src.core.entities import Timeframe

logger = logging.getLogger("AcquisitionAPI")

router = APIRouter(prefix="/acquisition", tags=["Data Acquisition"])

_task_manager: AcquisitionTaskManager | None = None


async def get_task_manager() -> AcquisitionTaskManager:
    """Retrieve or initialize singleton AcquisitionTaskManager."""
    global _task_manager
    if _task_manager is None:
        settings = get_settings()
        storage = await get_storage()

        env_name = getattr(settings, "env", "production")
        allow_mock = getattr(settings, "allow_mock_data", False)

        registry = ProviderRegistry(
            environment=env_name,
            allow_mock=allow_mock,
        )
        registry.register(AKShareProvider())

        if allow_mock and env_name != "production":
            registry.register(MockProvider())

        service = AcquisitionService(registry=registry, storage=storage)
        _task_manager = AcquisitionTaskManager(service=service, storage=storage)

        # On manager startup, clean up any zombie tasks left from ungraceful shutdown
        try:
            await _task_manager.cleanup_zombies()
        except Exception as sweep_err:
            logger.warning("Initial zombie sweep failed: %s", sweep_err)

    return _task_manager


# --------------------------------------------------------------------------- #
# Request & Response Schemas
# --------------------------------------------------------------------------- #


class CreateTaskRequest(BaseModel):
    symbols: list[str] = Field(
        ..., min_length=1, description="List of canonical stock symbols, e.g. ['600519.SH']"
    )
    timeframe: str = Field("1d", description="Target timeframe (1d, 1h, etc.)")
    start_date: str | None = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: str | None = Field(None, description="End date (YYYY-MM-DD)")
    provider_preference: str | None = Field(
        "auto", description="Preferred provider ID ('auto', 'akshare', 'mock')"
    )
    force_refresh: bool = Field(False, description="Whether to overwrite existing local data")


class TaskCreatedResponse(BaseModel):
    task_id: str
    status: str
    symbols_count: int
    created_at: str


class TaskCancelResponse(BaseModel):
    task_id: str
    status: str
    message: str


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.post(
    "/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskCreatedResponse,
    summary="Create and start an asynchronous data acquisition task",
)
async def create_acquisition_task(req: CreateTaskRequest) -> dict[str, Any]:
    manager = await get_task_manager()

    try:
        tf = Timeframe(req.timeframe)
    except ValueError as err:
        valid_tfs = [t.value for t in Timeframe]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported timeframe '{req.timeframe}'. Must be one of {valid_tfs}",
        ) from err

    start_dt = (
        datetime.strptime(req.start_date, "%Y-%m-%d").replace(tzinfo=UTC)
        if req.start_date
        else datetime(datetime.now(UTC).year - 1, 1, 1, tzinfo=UTC)
    )
    end_dt = (
        datetime.strptime(req.end_date, "%Y-%m-%d").replace(tzinfo=UTC)
        if req.end_date
        else datetime.now(UTC)
    )

    task_id = await manager.create_task(
        symbols=req.symbols,
        timeframe=tf,
        start_date=start_dt,
        end_date=end_dt,
        params={
            "provider_preference": req.provider_preference,
            "force_refresh": req.force_refresh,
        },
    )

    # Launch background worker
    manager.start_background_task(task_id)

    task_status = await manager.get_task_status(task_id)
    return {
        "task_id": task_id,
        "status": task_status.get("status", "PENDING") if task_status else "PENDING",
        "symbols_count": len(req.symbols),
        "created_at": task_status.get("created_at", "") if task_status else "",
    }


@router.get(
    "/tasks",
    summary="List acquisition tasks",
)
async def list_acquisition_tasks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    task_status: str | None = Query(None, alias="status"),
) -> dict[str, Any]:
    storage = await get_storage()
    tasks = await storage.sqlite.list_acquisition_tasks(
        limit=limit,
        offset=offset,
        status=task_status,
    )
    return {"tasks": tasks, "limit": limit, "offset": offset, "count": len(tasks)}


@router.get(
    "/tasks/{task_id}",
    summary="Get acquisition task details and progress",
)
async def get_acquisition_task_detail(task_id: str) -> dict[str, Any]:
    manager = await get_task_manager()
    status_rec = await manager.get_task_status(task_id)
    if not status_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Acquisition task '{task_id}' not found.",
        )
    return status_rec


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=TaskCancelResponse,
    summary="Cancel a running acquisition task",
)
async def cancel_acquisition_task(task_id: str) -> dict[str, str]:
    manager = await get_task_manager()
    status_rec = await manager.get_task_status(task_id)
    if not status_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Acquisition task '{task_id}' not found.",
        )

    await manager.cancel_task(task_id)
    return {
        "task_id": task_id,
        "status": "CANCELLED",
        "message": "Cancellation requested successfully.",
    }


@router.post(
    "/tasks/{task_id}/resume",
    summary="Directive 5: Resume an interrupted or partially failed task",
)
async def resume_acquisition_task(task_id: str) -> dict[str, Any]:
    manager = await get_task_manager()
    status_rec = await manager.get_task_status(task_id)
    if not status_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Acquisition task '{task_id}' not found.",
        )

    resumed = await manager.resume_task(task_id, background=True)
    msg = (
        "Task resumption initiated in background." if resumed else "Task already in SUCCESS state."
    )
    return {
        "task_id": task_id,
        "resumed": resumed,
        "message": msg,
    }


@router.post(
    "/tasks/cleanup-zombies",
    summary="Directive 1: Detect and clean up zombie acquisition tasks",
)
async def cleanup_zombie_tasks() -> dict[str, Any]:
    manager = await get_task_manager()
    cleaned = await manager.cleanup_zombies()
    return {"cleaned_zombie_tasks_count": cleaned}


@router.get(
    "/providers/health",
    summary="Probe connectivity of all registered data providers",
)
async def get_providers_health() -> dict[str, Any]:
    manager = await get_task_manager()
    results = {}
    for pid in manager.service.registry.list_providers():
        p = manager.service.registry.get_provider(pid)
        try:
            ok = await p.check_health()
            results[pid] = {"status": "UP" if ok else "DOWN"}
        except Exception as e:
            results[pid] = {"status": "ERROR", "detail": str(e)}
    return {"providers": results}
