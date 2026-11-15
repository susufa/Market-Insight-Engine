"""
tests/integration/test_acquisition_task_persistence.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Integration test suite verifying:
- Directive 1: Task SQLite persistence, heartbeat tracking, and zombie task detection
- Directive 5: Breakpoint resumption from checkpoint
- Raw response archival and provenance tracking in SQLite
"""

import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.acquisition.base import VolumeUnit
from src.acquisition.providers.mock_provider import MockProvider
from src.acquisition.registry import ProviderRegistry
from src.acquisition.service import AcquisitionService
from src.acquisition.task_manager import AcquisitionTaskManager
from src.core.entities import Timeframe
from src.storage.composite_engine import CompositeStorageEngine


@pytest.fixture
async def temp_env():
    temp_dir = Path(tempfile.mkdtemp(prefix="mie_acq_test_"))
    storage = CompositeStorageEngine(data_root=temp_dir, meta_db_path=temp_dir / "meta.db")
    await storage.initialise()

    registry = ProviderRegistry(environment="test", allow_mock=True)
    mock_p = MockProvider(volume_unit=VolumeUnit.SHARE)
    registry.register(mock_p)

    service = AcquisitionService(
        registry=registry, storage=storage, raw_storage_dir=temp_dir / "raw"
    )
    manager = AcquisitionTaskManager(service=service, storage=storage, concurrency=2)

    yield {
        "temp_dir": temp_dir,
        "storage": storage,
        "registry": registry,
        "service": service,
        "manager": manager,
        "mock_provider": mock_p,
    }

    await storage.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_task_creation_and_sqlite_persistence(temp_env):
    """Verify task and symbol items are persisted to SQLite."""
    manager: AcquisitionTaskManager = temp_env["manager"]
    storage: CompositeStorageEngine = temp_env["storage"]

    symbols = ["600519.SH", "000858.SZ", "000001.SZ"]
    task_id = await manager.create_task(
        symbols=symbols,
        timeframe=Timeframe.D1,
        start_date=datetime(2023, 1, 1, tzinfo=UTC),
        end_date=datetime(2023, 1, 10, tzinfo=UTC),
    )

    # Verify task in SQLite
    task_rec = await storage.sqlite.get_acquisition_task(task_id)
    assert task_rec is not None
    assert task_rec["task_id"] == task_id
    assert task_rec["status"] == "PENDING"
    assert task_rec["total_symbols"] == 3
    assert task_rec["completed_symbols"] == 0

    # Verify items in SQLite
    items = await storage.sqlite.get_acquisition_task_items(task_id)
    assert len(items) == 3
    item_symbols = {it["symbol"] for it in items}
    assert item_symbols == {"600519.SH", "000858.SZ", "000001.SZ"}
    for it in items:
        assert it["status"] == "PENDING"


@pytest.mark.asyncio
async def test_task_execution_and_raw_response_archival(temp_env):
    """Verify synchronous execution completes items and archives raw responses in SQLite."""
    manager: AcquisitionTaskManager = temp_env["manager"]
    storage: CompositeStorageEngine = temp_env["storage"]

    symbols = ["600519.SH", "000858.SZ"]
    task_id = await manager.create_task(
        symbols=symbols,
        timeframe=Timeframe.D1,
        start_date=datetime(2023, 1, 1, tzinfo=UTC),
        end_date=datetime(2023, 1, 10, tzinfo=UTC),
    )

    res = await manager.execute_task_synchronous(task_id)
    assert res["status"] == "SUCCESS"
    assert res["completed_symbols"] == 2
    assert res["failed_symbols"] == 0
    assert res["progress_percent"] == 100.0

    # Verify Parquet files were created
    p1 = temp_env["temp_dir"] / "production" / "CN_A" / "1d" / "600519.SH.parquet"
    p2 = temp_env["temp_dir"] / "production" / "CN_A" / "1d" / "000858.SZ.parquet"
    assert p1.exists()
    assert p2.exists()

    # Verify raw_response_audit records were created in SQLite
    async with storage.sqlite.conn.execute("SELECT COUNT(*) FROM raw_response_audit;") as cur:
        count = (await cur.fetchone())[0]
        assert count == 2


@pytest.mark.asyncio
async def test_zombie_task_detection_and_cleanup(temp_env):
    """Directive 1: Verify stale RUNNING task without heartbeat is marked INTERRUPTED."""
    manager: AcquisitionTaskManager = temp_env["manager"]
    storage: CompositeStorageEngine = temp_env["storage"]

    task_id = await manager.create_task(symbols=["600519.SH"])
    await storage.sqlite.update_acquisition_task_status(task_id, "RUNNING")

    # Manually backdate the heartbeat to 300 seconds ago
    stale_time = (datetime.now(UTC) - timedelta(seconds=300)).isoformat()
    await storage.sqlite.conn.execute(
        "UPDATE acquisition_tasks SET last_heartbeat_at = ? WHERE task_id = ?;",
        (stale_time, task_id),
    )
    await storage.sqlite.conn.commit()

    # Run zombie cleaner with 120s threshold
    cleaned = await manager.cleanup_zombies()
    assert cleaned == 1

    # Verify status is now INTERRUPTED
    task_rec = await storage.sqlite.get_acquisition_task(task_id)
    assert task_rec["status"] == "INTERRUPTED"
    assert "Heartbeat stale" in task_rec["error_message"]


@pytest.mark.asyncio
async def test_breakpoint_resumption_skips_success(temp_env):
    """Directive 5: Verify resume_task only executes pending/failed items, skipping success."""
    manager: AcquisitionTaskManager = temp_env["manager"]
    storage: CompositeStorageEngine = temp_env["storage"]

    symbols = ["600519.SH", "000858.SZ", "000001.SZ"]
    task_id = await manager.create_task(symbols=symbols)

    # Simulate 600519.SH already completed successfully
    await storage.sqlite.update_acquisition_task_item(
        task_id=task_id,
        symbol="600519.SH",
        status="SUCCESS",
        row_count=10,
        provider_used="mock",
    )
    # Simulate 000858.SZ was interrupted
    await storage.sqlite.update_acquisition_task_item(
        task_id=task_id,
        symbol="000858.SZ",
        status="FAILED",
        error_message="Simulated network drop",
    )
    # Mark master task as PARTIAL_SUCCESS / INTERRUPTED
    await storage.sqlite.update_acquisition_task_status(task_id, "INTERRUPTED")

    # Resume the task
    resumed = await manager.resume_task(task_id, background=False)
    assert resumed is True

    # Final status should now be SUCCESS for all
    final_status = await manager.get_task_status(task_id)
    assert final_status["status"] == "SUCCESS"
    assert final_status["completed_symbols"] == 3
    assert final_status["failed_symbols"] == 0
