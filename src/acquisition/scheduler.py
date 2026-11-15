"""
src/acquisition/scheduler.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Calendar-aware scheduled update orchestrator incorporating Directive 7:
Post-market publication buffer enforcement to avoid ingesting provisional/unsettled data.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any

from src.acquisition.task_manager import AcquisitionTaskManager
from src.core.entities import Market, Timeframe
from src.quality.calendar import TradingCalendar

logger = logging.getLogger("AcquisitionScheduler")


class AcquisitionScheduler:
    """
    Automated synchronization scheduler respecting trading calendars
    and official exchange publication settlement buffers.
    """

    # Chinese A-share trading session closes at 15:00 CST (07:00 UTC)
    MARKET_CLOSE_TIME_CST = time(15, 0)
    DEFAULT_BUFFER_MINUTES = 45  # Default wait until 15:45 CST

    def __init__(
        self,
        task_manager: AcquisitionTaskManager,
        market: Market = Market.CN_A,
        market_close_buffer_minutes: int = DEFAULT_BUFFER_MINUTES,
    ) -> None:
        self.task_manager = task_manager
        self.market = market
        self.buffer_minutes = max(0, market_close_buffer_minutes)
        self._running = False
        self._loop_task: asyncio.Task[Any] | None = None

    def evaluate_sync_window(
        self,
        current_dt_utc: datetime | None = None,
    ) -> tuple[bool, str]:
        """
        Evaluate whether current moment is eligible for post-close daily ingestion.
        Returns (is_eligible, explanation_reason).
        """
        now_utc = current_dt_utc or datetime.now(UTC)
        # Convert UTC to China Standard Time (UTC+8)
        cst_tz = timedelta(hours=8)
        now_cst = now_utc + cst_tz
        today_date = now_cst.date()

        # 1. Trading day check
        is_trading = TradingCalendar.is_trading_day(today_date, self.market)
        if not is_trading:
            return False, f"Date {today_date} is not a trading day for {self.market.value}."

        # 2. Market close + publication buffer check
        # Earliest allowable trigger time = 15:00 + buffer_minutes
        min_trigger_minute = self.MARKET_CLOSE_TIME_CST.minute + self.buffer_minutes
        min_trigger_hour = self.MARKET_CLOSE_TIME_CST.hour + (min_trigger_minute // 60)
        min_trigger_minute = min_trigger_minute % 60
        earliest_trigger = time(min_trigger_hour, min_trigger_minute)

        curr_time = now_cst.time()
        if curr_time < earliest_trigger:
            return (
                False,
                f"Market publication buffer active: current CST time {curr_time.strftime('%H:%M')} "
                f"is earlier than settlement threshold {earliest_trigger.strftime('%H:%M')} "
                f"(buffer={self.buffer_minutes}m).",
            )

        return True, "Eligible for daily settlement sync."

    async def trigger_daily_update(
        self,
        symbols: list[str],
        force_ignore_calendar: bool = False,
    ) -> str | None:
        """
        Trigger scheduled daily bar sync for the given universe.
        """
        if not force_ignore_calendar:
            eligible, reason = self.evaluate_sync_window()
            if not eligible:
                logger.info("Daily sync skipped: %s", reason)
                return None

        now_utc = datetime.now(UTC)
        start_date = now_utc - timedelta(days=30)  # Sync last 30 days incrementally

        task_id = await self.task_manager.create_task(
            symbols=symbols,
            timeframe=Timeframe.D1,
            start_date=start_date,
            end_date=now_utc,
            params={
                "trigger": "scheduled_daily_sync",
                "buffer_minutes": self.buffer_minutes,
            },
        )

        self.task_manager.start_background_task(task_id)
        logger.info("Scheduled daily sync task %s initiated for %d symbols", task_id, len(symbols))
        return task_id
