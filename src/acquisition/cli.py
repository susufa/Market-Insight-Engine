"""
src/acquisition/cli.py
~~~~~~~~~~~~~~~~~~~~~~
Standalone command-line tool for Market Insight Engine data acquisition.
Enables independent batch operations, breakpoint resumption, and zombie task maintenance
without starting the FastAPI web service.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from config import get_settings
from src.acquisition.providers.akshare_provider import AKShareProvider
from src.acquisition.providers.mock_provider import MockProvider
from src.acquisition.registry import ProviderRegistry
from src.acquisition.service import AcquisitionService
from src.acquisition.task_manager import AcquisitionTaskManager
from src.core.entities import Timeframe
from src.storage.composite_engine import CompositeStorageEngine


def setup_engine_and_manager(
    allow_mock: bool = False,
) -> tuple[CompositeStorageEngine, AcquisitionTaskManager]:
    """Initialize storage engine, provider registry, and task manager."""
    settings = get_settings()
    storage = CompositeStorageEngine()

    env_name = getattr(settings, "env", "production")
    allow_mock_flag = allow_mock or getattr(settings, "allow_mock_data", False)

    registry = ProviderRegistry(
        environment=env_name,
        allow_mock=allow_mock_flag,
    )

    # Register AKShare provider
    registry.register(AKShareProvider())

    # Register mock only if explicitly allowed and not production
    if allow_mock_flag and env_name != "production":
        registry.register(MockProvider())

    service = AcquisitionService(registry=registry, storage=storage)
    manager = AcquisitionTaskManager(service=service, storage=storage)

    return storage, manager


def format_progress_bar(current: int, total: int, width: int = 30) -> str:
    """ASCII progress bar."""
    if total <= 0:
        return "[------------------------------] 0%"
    pct = min(max(current / total, 0.0), 1.0)
    filled = int(width * pct)
    bar = "=" * filled + (">" if filled < width else "") + "-" * max(0, width - filled - 1)
    return f"[{bar[:width]}] {pct * 100:.1f}% ({current}/{total})"


async def cmd_fetch(args: argparse.Namespace) -> int:
    """Fetch bars for a single symbol."""
    storage, manager = setup_engine_and_manager(allow_mock=args.mock)
    await storage.initialise()

    try:
        start = (
            datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
            if args.start
            else datetime(datetime.now(UTC).year - 1, 1, 1, tzinfo=UTC)
        )
        end = (
            datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)
            if args.end
            else datetime.now(UTC)
        )
        tf = Timeframe(args.timeframe)

        print(f"Fetching '{args.symbol}' ({tf.value}) from {start.date()} to {end.date()}...")
        task_id = await manager.create_task(
            symbols=[args.symbol],
            timeframe=tf,
            start_date=start,
            end_date=end,
            params={"provider_preference": args.provider},
        )

        def _on_progress(done: int, total: int, sym: str, msg: str) -> None:
            print(f"  {format_progress_bar(done, total)} | {sym}: {msg}")

        res = await manager.execute_task_synchronous(task_id, progress_callback=_on_progress)
        print(f"\nTask Finished with status: {res.get('status')}")
        if res.get("status") in ("SUCCESS", "PARTIAL_SUCCESS"):
            return 0
        return 1
    finally:
        await storage.close()


async def cmd_batch(args: argparse.Namespace) -> int:
    """Fetch bars for a batch of symbols."""
    storage, manager = setup_engine_and_manager(allow_mock=args.mock)
    await storage.initialise()

    try:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        if not symbols:
            print("Error: No symbols provided.")
            return 1

        start = (
            datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
            if args.start
            else datetime(datetime.now(UTC).year - 1, 1, 1, tzinfo=UTC)
        )
        end = (
            datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)
            if args.end
            else datetime.now(UTC)
        )
        tf = Timeframe(args.timeframe)

        print(f"Starting batch acquisition of {len(symbols)} symbols ({tf.value})...")
        task_id = await manager.create_task(
            symbols=symbols,
            timeframe=tf,
            start_date=start,
            end_date=end,
            params={"provider_preference": args.provider},
        )
        print(f"Created Task ID: {task_id}\n")

        def _on_progress(done: int, total: int, sym: str, msg: str) -> None:
            print(f"  {format_progress_bar(done, total)} | {sym}: {msg}")

        res = await manager.execute_task_synchronous(task_id, progress_callback=_on_progress)
        print(f"\nBatch Completed. Final status: {res.get('status')}")
        print(f"  Success: {res.get('completed_symbols', 0)} / {res.get('total_symbols', 0)}")
        print(f"  Failed:  {res.get('failed_symbols', 0)}")
        return 0 if res.get("status") in ("SUCCESS", "PARTIAL_SUCCESS") else 1
    finally:
        await storage.close()


async def cmd_resume(args: argparse.Namespace) -> int:
    """Directive 5: Resume an interrupted task from SQLite checkpoint."""
    storage, manager = setup_engine_and_manager()
    await storage.initialise()

    try:
        task_id = args.task_id
        print(f"Attempting breakpoint resumption for Task ID: {task_id}...")
        status_before = await manager.get_task_status(task_id)
        if not status_before:
            print(f"Error: Task {task_id} not found in database.")
            return 1

        completed = status_before["completed_symbols"]
        total = status_before["total_symbols"]
        print(f"Current State: {status_before['status']} ({completed}/{total})")

        def _on_progress(done: int, total: int, sym: str, msg: str) -> None:
            print(f"  {format_progress_bar(done, total)} | {sym}: {msg}")

        # Execute resume synchronously
        await manager.resume_task(task_id, background=False)
        status_after = await manager.get_task_status(task_id)
        new_st = status_after.get("status") if status_after else "N/A"
        print(f"\nResume Finished. New status: {new_st}")
        return 0
    finally:
        await storage.close()


async def cmd_status(args: argparse.Namespace) -> int:
    """Query task status and items breakdown."""
    storage, manager = setup_engine_and_manager()
    await storage.initialise()

    try:
        res = await manager.get_task_status(args.task_id)
        if not res:
            print(f"Task '{args.task_id}' not found.")
            return 1

        print(f"Task ID:          {res['task_id']}")
        print(f"Status:           {res['status']}")
        print(f"Timeframe:        {res['timeframe']}")
        print(f"Date Range:       {res['start_date']} to {res['end_date']}")
        done_syms = res["completed_symbols"]
        tot_syms = res["total_symbols"]
        print(f"Progress:         {res['progress_percent']:.1f}% ({done_syms}/{tot_syms})")
        print(f"Last Heartbeat:   {res['last_heartbeat_at']}")
        if res.get("error_message"):
            print(f"Error Message:    {res['error_message']}")

        print("\nSymbol Breakdown:")
        for it in res.get("items", []):
            st = it["status"]
            lat = f"{it['execution_latency_ms']:.0f}ms" if it.get("execution_latency_ms") else "-"
            rows = f"{it['row_count']} rows" if it.get("row_count") else "-"
            src = it.get("source_interface", "")
            print(f"  - {it['symbol']:<10} [{st:<7}] {rows:<10} {lat:<8} {src}")
        return 0
    finally:
        await storage.close()


async def cmd_cleanup_zombies(args: argparse.Namespace) -> int:
    """Directive 1: Sweep and mark zombie tasks."""
    storage, manager = setup_engine_and_manager()
    await storage.initialise()

    try:
        count = await manager.cleanup_zombies()
        print(f"Zombie Task Sweep complete. {count} stale tasks cleaned up.")
        return 0
    finally:
        await storage.close()


async def cmd_health(args: argparse.Namespace) -> int:
    """Probe connectivity for all registered providers."""
    storage, manager = setup_engine_and_manager(allow_mock=args.mock)
    await storage.initialise()

    try:
        print("Checking provider health...")
        for pid in manager.service.registry.list_providers():
            p = manager.service.registry.get_provider(pid)
            try:
                ok = await p.check_health()
                status_str = "[OK]" if ok else "[FAIL]"
            except Exception as e:
                status_str = f"[ERROR: {e}]"
            print(f"  {pid:<15}: {status_str}")
        return 0
    finally:
        await storage.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.acquisition.cli",
        description="Market Insight Engine - Modular Data Acquisition CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch a single security")
    p_fetch.add_argument("--symbol", required=True, help="Security symbol, e.g. 600519.SH")
    p_fetch.add_argument("--timeframe", default="1d", help="Timeframe (default: 1d)")
    p_fetch.add_argument("--start", help="Start date (YYYY-MM-DD)")
    p_fetch.add_argument("--end", help="End date (YYYY-MM-DD)")
    p_fetch.add_argument("--provider", default="auto", help="Provider preference (default: auto)")
    p_fetch.add_argument("--mock", action="store_true", help="Allow MockProvider in non-prod")

    # batch
    p_batch = subparsers.add_parser("batch", help="Batch fetch multiple securities")
    p_batch.add_argument(
        "--symbols", required=True, help="Comma-separated symbols, e.g. 600519.SH,000858.SZ"
    )
    p_batch.add_argument("--timeframe", default="1d", help="Timeframe (default: 1d)")
    p_batch.add_argument("--start", help="Start date (YYYY-MM-DD)")
    p_batch.add_argument("--end", help="End date (YYYY-MM-DD)")
    p_batch.add_argument("--provider", default="auto", help="Provider preference (default: auto)")
    p_batch.add_argument("--mock", action="store_true", help="Allow MockProvider in non-prod")

    # resume
    p_resume = subparsers.add_parser("resume", help="Resume interrupted task from checkpoint")
    p_resume.add_argument("--task-id", required=True, help="Task ID to resume")

    # status
    p_status = subparsers.add_parser("status", help="Check status of a task")
    p_status.add_argument("--task-id", required=True, help="Task ID to inspect")

    # cleanup-zombies
    subparsers.add_parser("cleanup-zombies", help="Clean up stale/zombie acquisition tasks")

    # health
    p_health = subparsers.add_parser("health", help="Check health of data providers")
    p_health.add_argument("--mock", action="store_true", help="Include MockProvider in check")

    args = parser.parse_args()

    cmd_map = {
        "fetch": cmd_fetch,
        "batch": cmd_batch,
        "resume": cmd_resume,
        "status": cmd_status,
        "cleanup-zombies": cmd_cleanup_zombies,
        "health": cmd_health,
    }

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        exit_code = loop.run_until_complete(cmd_map[args.command](args))
        sys.exit(exit_code)
    finally:
        loop.close()


if __name__ == "__main__":
    main()
