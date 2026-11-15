"""
src/acquisition/task_manager.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Asynchronous Acquisition Task Manager providing:
- Directive 1: Full SQLite persistence, heartbeat tracking, and zombie task detection
- Directive 5: Timeout sharding, 20-minute hard limit guard, and breakpoint resumption
- Non-blocking async queue with concurrency gating and cancellation tokens
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from src.acquisition.service import AcquisitionService
from src.core.entities import Timeframe
from src.storage.composite_engine import CompositeStorageEngine

logger = logging.getLogger("AcquisitionTaskManager")


class AcquisitionTaskManager:
    """
    Manages background data acquisition tasks with SQLite state persistence,
    heartbeat monitoring, zombie task sweeping, and breakpoint recovery.
    """

    HEARTBEAT_INTERVAL_SECONDS = 5.0
    ZOMBIE_TIMEOUT_SECONDS = 120.0
    TASK_HARD_TIMEOUT_SECONDS = 1200.0  # 20 minutes maximum per task

    def __init__(
        self,
        service: AcquisitionService,
        storage: CompositeStorageEngine,
        concurrency: int = 2,
    ) -> None:
        self.service = service
        self.storage = storage
        self.concurrency = max(1, concurrency)
        self._cancellation_events: dict[str, asyncio.Event] = {}
        self._running_tasks: dict[str, asyncio.Task[Any]] = {}

    def generate_task_id(self) -> str:
        """Generate human-readable unique task identifier."""
        now_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        rand_suffix = uuid.uuid4().hex[:6]
        return f"acq_{now_str}_{rand_suffix}"

    async def create_task(
        self,
        symbols: list[str],
        timeframe: Timeframe = Timeframe.D1,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a new persistent acquisition task in SQLite.
        """
        now = datetime.now(UTC)
        start = start_date or datetime(now.year - 1, 1, 1, tzinfo=UTC)
        end = end_date or now

        task_id = self.generate_task_id()
        clean_symbols = [s.upper().strip() for s in symbols if s.strip()]

        await self.storage.sqlite.create_acquisition_task(
            task_id=task_id,
            symbols=clean_symbols,
            timeframe=timeframe.value,
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            params=params or {},
        )

        self._cancellation_events[task_id] = asyncio.Event()
        logger.info(
            "Created persistent acquisition task %s with %d symbols",
            task_id,
            len(clean_symbols),
        )
        return task_id

    def start_background_task(self, task_id: str) -> None:
        """Launch background worker for task_id."""
        task = asyncio.create_task(self._execute_task_pipeline(task_id))
        self._running_tasks[task_id] = task

        def _cleanup_callback(fut: asyncio.Future[Any]) -> None:
            self._running_tasks.pop(task_id, None)
            self._cancellation_events.pop(task_id, None)
            if fut.exception():
                logger.error(
                    "Background task %s failed with exception: %s",
                    task_id,
                    fut.exception(),
                )

        task.add_done_callback(_cleanup_callback)

    async def execute_task_synchronous(
        self,
        task_id: str,
        progress_callback: Callable[[int, int, str, str], None] | None = None,
    ) -> dict[str, Any]:
        """
        Execute task synchronously (e.g. for CLI usage or blocking test drills).
        """
        if task_id not in self._cancellation_events:
            self._cancellation_events[task_id] = asyncio.Event()
        await self._execute_task_pipeline(task_id, progress_callback=progress_callback)
        status = await self.get_task_status(task_id)
        return status or {}

    async def cancel_task(self, task_id: str) -> bool:
        """Request graceful cancellation of a running task."""
        if task_id in self._cancellation_events:
            self._cancellation_events[task_id].set()

        await self.storage.sqlite.update_acquisition_task_status(
            task_id=task_id,
            status="CANCELLED",
            error_message="User requested task cancellation",
        )
        logger.info("Task %s cancellation requested", task_id)
        return True

    async def resume_task(
        self,
        task_id: str,
        background: bool = True,
    ) -> bool:
        """
        Directive 5: Resume an interrupted or partially failed task from SQLite checkpoint.
        Skips already completed items and resumes pending/failed items.
        """
        task_rec = await self.storage.sqlite.get_acquisition_task(task_id)
        if not task_rec:
            raise ValueError(f"Task '{task_id}' not found in database.")

        if task_rec["status"] == "SUCCESS":
            logger.info("Task %s already succeeded; nothing to resume.", task_id)
            return False

        self._cancellation_events[task_id] = asyncio.Event()
        if background:
            self.start_background_task(task_id)
        else:
            await self._execute_task_pipeline(task_id)
        return True

    async def cleanup_zombies(self) -> int:
        """
        Directive 1: Detect and clean up zombie tasks.
        """
        count: int = await self.storage.sqlite.cleanup_zombie_tasks(self.ZOMBIE_TIMEOUT_SECONDS)
        if count > 0:
            logger.warning("Cleaned up %d zombie acquisition tasks from SQLite", count)
        return int(count)

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Retrieve task details and item breakdown from SQLite."""
        task_rec: dict[str, Any] | None = await self.storage.sqlite.get_acquisition_task(task_id)
        if not task_rec:
            return None
        items = await self.storage.sqlite.get_acquisition_task_items(task_id)
        task_rec["items"] = items

        # Compute progress percentage
        total = int(task_rec["total_symbols"])
        done = int(task_rec["completed_symbols"]) + int(task_rec["failed_symbols"])
        task_rec["progress_percent"] = (done / total * 100.0) if total > 0 else 100.0
        return task_rec

    # ------------------------------------------------------------------ #
    # Internal Execution Engine
    # ------------------------------------------------------------------ #

    async def _heartbeat_loop(self, task_id: str, cancel_ev: asyncio.Event) -> None:
        """Continuously update last_heartbeat_at while task is actively running."""
        try:
            while not cancel_ev.is_set():
                await self.storage.sqlite.update_acquisition_task_heartbeat(task_id)
                await asyncio.sleep(self.HEARTBEAT_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            pass

    async def _execute_task_pipeline(
        self,
        task_id: str,
        progress_callback: Callable[[int, int, str, str], None] | None = None,
    ) -> None:
        """Core execution worker with 20-minute timeout guard and item checkpointing."""
        task_rec = await self.storage.sqlite.get_acquisition_task(task_id)
        if not task_rec:
            logger.error("Cannot run task %s: not found in SQLite", task_id)
            return

        cancel_ev = self._cancellation_events.get(task_id, asyncio.Event())
        await self.storage.sqlite.update_acquisition_task_status(task_id, "RUNNING")

        # Start heartbeat
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(task_id, cancel_ev))

        timeframe = Timeframe(task_rec["timeframe"])
        start = datetime.strptime(task_rec["start_date"], "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(task_rec["end_date"], "%Y-%m-%d").replace(tzinfo=UTC)
        params = task_rec.get("params", {})
        provider_pref = params.get("provider_preference")

        items = await self.storage.sqlite.get_acquisition_task_items(task_id)
        # Filter items to process (Directive 5: skip already SUCCESS items)
        pending_items = [it for it in items if it["status"] != "SUCCESS"]

        total_count = len(items)
        completed_count = len([it for it in items if it["status"] == "SUCCESS"])
        failed_count = len([it for it in items if it["status"] == "FAILED"])

        semaphore = asyncio.Semaphore(self.concurrency)

        try:
            # Wrap entire batch in hard 20-minute timeout guard
            async with asyncio.timeout(self.TASK_HARD_TIMEOUT_SECONDS):
                for item in pending_items:
                    if cancel_ev.is_set():
                        logger.info("Task %s cancellation detected; stopping item loop.", task_id)
                        break

                    sym = item["symbol"]
                    async with semaphore:
                        t0 = datetime.now(UTC)
                        try:
                            # 15s per-symbol acquisition timeout
                            bars, spec, archive = await asyncio.wait_for(
                                self.service.acquire_bars(
                                    symbol=sym,
                                    timeframe=timeframe,
                                    start=start,
                                    end=end,
                                    provider_preference=provider_pref,
                                ),
                                timeout=30.0,
                            )
                            t1 = datetime.now(UTC)
                            lat = (t1 - t0).total_seconds() * 1000.0

                            await self.storage.sqlite.update_acquisition_task_item(
                                task_id=task_id,
                                symbol=sym,
                                status="SUCCESS",
                                row_count=len(bars),
                                provider_used=archive.provider_name,
                                source_interface=archive.source_interface,
                                latency_ms=lat,
                            )
                            completed_count += 1
                            if progress_callback:
                                progress_callback(completed_count, total_count, sym, "SUCCESS")

                        except Exception as item_err:
                            t1 = datetime.now(UTC)
                            lat = (t1 - t0).total_seconds() * 1000.0
                            logger.warning(
                                "Acquisition failed for item %s in task %s: %s",
                                sym,
                                task_id,
                                item_err,
                            )
                            await self.storage.sqlite.update_acquisition_task_item(
                                task_id=task_id,
                                symbol=sym,
                                status="FAILED",
                                latency_ms=lat,
                                error_message=str(item_err)[:300],
                            )
                            failed_count += 1
                            if progress_callback:
                                progress_callback(
                                    completed_count, total_count, sym, f"FAILED: {item_err}"
                                )

                    # Yield execution briefly
                    await asyncio.sleep(0.05)

        except TimeoutError:
            err_msg = (
                f"Task exceeded hard execution limit of {self.TASK_HARD_TIMEOUT_SECONDS}s. "
                "Force stopped."
            )
            logger.error(err_msg)
            await self.storage.sqlite.update_acquisition_task_status(
                task_id, "FAILED", error_message=err_msg
            )
            return
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

        # Final task status resolution
        if cancel_ev.is_set():
            final_status = "CANCELLED"
            err = "Task was cancelled before completion"
        elif completed_count == total_count:
            final_status = "SUCCESS"
            err = None
        elif completed_count > 0:
            final_status = "PARTIAL_SUCCESS"
            err = f"{failed_count} of {total_count} symbols failed"
        else:
            final_status = "FAILED"
            err = f"All {total_count} symbols failed"

        await self.storage.sqlite.update_acquisition_task_status(
            task_id=task_id,
            status=final_status,
            error_message=err,
        )
        logger.info(
            "Task %s finished with status '%s' (completed=%d, failed=%d, total=%d)",
            task_id,
            final_status,
            completed_count,
            failed_count,
            total_count,
        )
