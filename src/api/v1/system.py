"""
api/v1/system.py
~~~~~~~~~~~~~~~~
System health, status, and configuration endpoints.

GET /api/v1/system/health   – liveness probe
GET /api/v1/system/info     – runtime info (version, paths, settings summary)
"""

from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from config import get_settings

router = APIRouter(prefix="/system", tags=["System"])


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str


class SystemInfoResponse(BaseModel):
    version: str
    env: str
    python_version: str
    platform: str
    data_root: str
    gpu_enabled: bool
    max_worker_threads: int


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe – returns 200 when the service is running."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(UTC),
        version="0.10.0",
    )


@router.get("/info", response_model=SystemInfoResponse)
async def system_info() -> SystemInfoResponse:
    """Return current runtime configuration summary."""
    s = get_settings()
    return SystemInfoResponse(
        version="0.10.0",
        env=s.env,
        python_version=sys.version,
        platform=platform.platform(),
        data_root=str(s.data_root),
        gpu_enabled=s.enable_gpu,
        max_worker_threads=s.max_worker_threads,
    )
