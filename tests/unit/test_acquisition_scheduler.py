"""
tests/unit/test_acquisition_scheduler.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit test suite verifying Directive 7:
Market close publication buffer and calendar-aware scheduling.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.acquisition.scheduler import AcquisitionScheduler
from src.core.entities import Market


@pytest.fixture
def mock_task_manager():
    mgr = MagicMock()
    mgr.create_task = AsyncMock(return_value="acq_mock_task_001")
    mgr.start_background_task = MagicMock()
    return mgr


def test_scheduler_skips_weekend(mock_task_manager):
    """Verify scheduler rejects triggering on Saturday or Sunday."""
    scheduler = AcquisitionScheduler(task_manager=mock_task_manager, market=Market.CN_A)

    # 2024-04-06 is Saturday (CST)
    saturday_utc = datetime(2024, 4, 6, 8, 0, tzinfo=UTC)  # 16:00 CST
    eligible, reason = scheduler.evaluate_sync_window(current_dt_utc=saturday_utc)

    assert eligible is False
    assert "not a trading day" in reason


def test_scheduler_blocks_before_buffer_time(mock_task_manager):
    """Directive 7: Verify scheduler blocks trigger when within buffer period (e.g. 15:10 CST)."""
    scheduler = AcquisitionScheduler(
        task_manager=mock_task_manager,
        market=Market.CN_A,
        market_close_buffer_minutes=45,  # Earliest = 15:45 CST
    )

    # 2024-04-08 is Monday. 07:15 UTC = 15:15 CST (within buffer)
    trading_monday_in_buffer = datetime(2024, 4, 8, 7, 15, tzinfo=UTC)
    eligible, reason = scheduler.evaluate_sync_window(current_dt_utc=trading_monday_in_buffer)

    assert eligible is False
    assert "buffer active" in reason
    assert "15:45" in reason


def test_scheduler_allows_after_buffer_time(mock_task_manager):
    """Directive 7: Verify scheduler allows trigger after buffer period (e.g. 15:50 CST)."""
    scheduler = AcquisitionScheduler(
        task_manager=mock_task_manager,
        market=Market.CN_A,
        market_close_buffer_minutes=45,  # Earliest = 15:45 CST
    )

    # 2024-04-08 is Monday. 07:50 UTC = 15:50 CST (post-buffer)
    trading_monday_post_buffer = datetime(2024, 4, 8, 7, 50, tzinfo=UTC)
    eligible, reason = scheduler.evaluate_sync_window(current_dt_utc=trading_monday_post_buffer)

    assert eligible is True
    assert "Eligible" in reason


@pytest.mark.asyncio
async def test_trigger_daily_update_executes_task(mock_task_manager):
    """Verify trigger_daily_update initiates background task when eligible."""
    scheduler = AcquisitionScheduler(task_manager=mock_task_manager, market=Market.CN_A)

    with pytest.MonkeyPatch.context() as m:
        m.setattr(scheduler, "evaluate_sync_window", lambda: (True, "Eligible"))
        task_id = await scheduler.trigger_daily_update(["600519.SH", "000858.SZ"])

        assert task_id == "acq_mock_task_001"
        mock_task_manager.create_task.assert_called_once()
        mock_task_manager.start_background_task.assert_called_once_with("acq_mock_task_001")
