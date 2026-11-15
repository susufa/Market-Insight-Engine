"""
core/interfaces/quality.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Abstract contract for the Data Quality Manager (DQM).

The DQM is the sole gatekeeper between the Staging zone and the
Production zone.  No data may enter Production without passing through
a concrete implementation of this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.entities import DataQualityReport, MarketBar, Timeframe


class BaseQualityValidator(ABC):
    """
    Port definition for the data quality validation layer.

    A validator receives a batch of raw bars (all same symbol +
    timeframe) and returns a `DataQualityReport`.  Callers decide
    what to do based on `report.status`:
    - PASS    → commit to production
    - WARNING → commit with caveat flag
    - REJECT  → route to quarantine
    """

    @abstractmethod
    def validate(
        self,
        bars: list[MarketBar],
        timeframe: Timeframe,
        *,
        existing_bars: list[MarketBar] | None = None,
    ) -> DataQualityReport:
        """
        Run all quality rules against `bars`.

        Parameters
        ----------
        bars          : Incoming bar batch for a single symbol.
        timeframe     : Declared frequency (used for calendar checks).
        existing_bars : Currently stored bars for this symbol, used for
                        conflict / regression detection.  May be None if
                        no prior data exists.

        Returns
        -------
        DataQualityReport with per-rule violations and overall status.
        """
