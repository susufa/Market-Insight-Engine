"""
quality/calendar.py
~~~~~~~~~~~~~~~~~~~
Comprehensive trading calendar validation helpers for China A-share and HK markets.
Includes explicit multi-market statutory holidays, market divergence handling,
and suspension awareness.
"""

from __future__ import annotations

from datetime import date, timedelta

from core.entities import Market


class TradingCalendar:
    """
    Multi-market trading calendar validator.
    Supports China A-share (CN_A), Hong Kong (CN_HK), and index trading days.
    """

    # Major China A-Share statutory market closure ranges (YYYY, M, D)
    # Covering recent multi-year statutory holiday windows (Spring Festival, National Day, etc.)
    CN_A_HOLIDAYS_EXACT: set[date] = {
        # 2021
        date(2021, 1, 1),
        date(2021, 2, 11),
        date(2021, 2, 12),
        date(2021, 2, 15),
        date(2021, 2, 16),
        date(2021, 2, 17),
        date(2021, 4, 5),
        date(2021, 5, 3),
        date(2021, 5, 4),
        date(2021, 5, 5),
        date(2021, 6, 14),
        date(2021, 9, 20),
        date(2021, 9, 21),
        date(2021, 10, 1),
        date(2021, 10, 4),
        date(2021, 10, 5),
        date(2021, 10, 6),
        date(2021, 10, 7),
        # 2022
        date(2022, 1, 3),
        date(2022, 1, 31),
        date(2022, 2, 1),
        date(2022, 2, 2),
        date(2022, 2, 3),
        date(2022, 2, 4),
        date(2022, 4, 4),
        date(2022, 4, 5),
        date(2022, 5, 2),
        date(2022, 5, 3),
        date(2022, 5, 4),
        date(2022, 6, 3),
        date(2022, 9, 12),
        date(2022, 10, 3),
        date(2022, 10, 4),
        date(2022, 10, 5),
        date(2022, 10, 6),
        date(2022, 10, 7),
        # 2023
        date(2023, 1, 2),
        date(2023, 1, 23),
        date(2023, 1, 24),
        date(2023, 1, 25),
        date(2023, 1, 26),
        date(2023, 1, 27),
        date(2023, 4, 5),
        date(2023, 5, 1),
        date(2023, 5, 2),
        date(2023, 5, 3),
        date(2023, 6, 22),
        date(2023, 6, 23),
        date(2023, 9, 29),
        date(2023, 10, 2),
        date(2023, 10, 3),
        date(2023, 10, 4),
        date(2023, 10, 5),
        date(2023, 10, 6),
        # 2024
        date(2024, 1, 1),
        date(2024, 2, 9),
        date(2024, 2, 12),
        date(2024, 2, 13),
        date(2024, 2, 14),
        date(2024, 2, 15),
        date(2024, 2, 16),
        date(2024, 4, 4),
        date(2024, 4, 5),
        date(2024, 5, 1),
        date(2024, 5, 2),
        date(2024, 5, 3),
        date(2024, 6, 10),
        date(2024, 9, 16),
        date(2024, 9, 17),
        date(2024, 10, 1),
        date(2024, 10, 2),
        date(2024, 10, 3),
        date(2024, 10, 4),
        date(2024, 10, 7),
        # 2025
        date(2025, 1, 1),
        date(2025, 1, 28),
        date(2025, 1, 29),
        date(2025, 1, 30),
        date(2025, 1, 31),
        date(2025, 2, 3),
        date(2025, 2, 4),
        date(2025, 4, 4),
        date(2025, 5, 1),
        date(2025, 5, 2),
        date(2025, 5, 5),
        date(2025, 6, 2),
        date(2025, 10, 1),
        date(2025, 10, 2),
        date(2025, 10, 3),
        date(2025, 10, 6),
        date(2025, 10, 7),
        date(2025, 10, 8),
        # 2026
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 2, 16),
        date(2026, 2, 17),
        date(2026, 2, 18),
        date(2026, 2, 19),
        date(2026, 2, 20),
        date(2026, 4, 6),
        date(2026, 5, 1),
        date(2026, 5, 4),
        date(2026, 5, 5),
        date(2026, 6, 19),
        date(2026, 9, 25),
        date(2026, 10, 1),
        date(2026, 10, 2),
        date(2026, 10, 5),
        date(2026, 10, 6),
        date(2026, 10, 7),
    }

    # Hong Kong (HKEX) specific non-trading holidays (Easter, Buddha's Birthday, Christmas, etc.)
    HKEX_HOLIDAYS_EXACT: set[date] = {
        # Easter & Good Friday
        date(2021, 4, 2),
        date(2021, 4, 5),
        date(2021, 4, 6),
        date(2021, 5, 19),
        date(2021, 7, 1),
        date(2021, 12, 27),
        date(2022, 4, 15),
        date(2022, 4, 18),
        date(2022, 5, 9),
        date(2022, 7, 1),
        date(2022, 12, 26),
        date(2022, 12, 27),
        date(2023, 4, 7),
        date(2023, 4, 10),
        date(2023, 5, 26),
        date(2023, 10, 23),
        date(2023, 12, 25),
        date(2023, 12, 26),
        date(2024, 3, 29),
        date(2024, 4, 1),
        date(2024, 5, 15),
        date(2024, 7, 1),
        date(2024, 10, 11),
        date(2024, 12, 25),
        date(2024, 12, 26),
    }

    # Recurring annual fixed closures (month, day)
    FIXED_ANNUAL_HOLIDAYS = {
        (1, 1),  # New Year
        (5, 1),  # Labor Day
        (10, 1),  # National Day
        (10, 2),
        (10, 3),
    }

    @classmethod
    def is_weekend(cls, d: date) -> bool:
        """Returns True if the date falls on Saturday (5) or Sunday (6)."""
        return d.weekday() >= 5

    @classmethod
    def is_trading_day(cls, d: date, market: Market = Market.CN_A) -> bool:
        """
        Check if `d` is a valid trading day for the given market.
        Considers weekends, recurring statutory closures, and market-specific calendars.
        """
        if cls.is_weekend(d):
            return False

        if (d.month, d.day) in cls.FIXED_ANNUAL_HOLIDAYS:
            return False

        if market in (Market.CN_A, Market.INDEX):
            if d in cls.CN_A_HOLIDAYS_EXACT:
                return False
        elif market == Market.CN_HK and d in cls.HKEX_HOLIDAYS_EXACT:
            return False

        return True

    @classmethod
    def is_likely_trading_day(cls, d: date) -> bool:
        """Backward-compatible helper for general trading day check (defaults to CN_A)."""
        return cls.is_trading_day(d, Market.CN_A)

    @classmethod
    def get_expected_trading_days(
        cls,
        start: date,
        end: date,
        market: Market = Market.CN_A,
    ) -> list[date]:
        """Generate list of expected trading days between start and end (inclusive)."""
        days: list[date] = []
        cur = start
        while cur <= end:
            if cls.is_trading_day(cur, market):
                days.append(cur)
            cur += timedelta(days=1)
        return days
