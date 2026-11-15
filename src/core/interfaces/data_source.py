"""
core/interfaces/data_source.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Abstract contract that every data source adapter MUST implement.

Anti-corruption rule
--------------------
Adapters translate raw external responses into canonical entities
(`Security`, `MarketBar`) defined in `core.entities`.  No external
library types (e.g. akshare DataFrames) may cross this boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from core.entities import AdjustmentEvent, Market, MarketBar, Security, Timeframe


class BaseDataSourceAdapter(ABC):
    """
    Port definition for all external market-data adapters.

    Each concrete adapter (e.g. AKShareAdapter) must implement every
    @abstractmethod without raising NotImplementedError at runtime.
    """

    # ------------------------------------------------------------------ #
    # Identity & capability metadata
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique stable identifier for this adapter, e.g. 'akshare'."""

    @property
    @abstractmethod
    def supported_markets(self) -> list[Market]:
        """Markets this adapter can serve data for."""

    @property
    @abstractmethod
    def supported_timeframes(self) -> list[Timeframe]:
        """Bar frequencies this adapter natively supports."""

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def check_health(self) -> bool:
        """
        Perform a lightweight connectivity / sanity check.

        Returns True when the source is reachable and returns valid data.
        Should NOT raise; return False on any failure.
        """

    # ------------------------------------------------------------------ #
    # Security list
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def fetch_security_list(self, market: Market) -> list[Security]:
        """
        Return the full listing of securities available for `market`.

        Raises
        ------
        DataSourceUnavailableError   – network or server failure
        DataSourceSchemaChangedError – unexpected response structure
        """

    # ------------------------------------------------------------------ #
    # Historical bar data
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def fetch_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        """
        Fetch OHLCV bars for `symbol` over [start, end] (inclusive).

        Parameters
        ----------
        symbol    : Canonical symbol, e.g. '600519.SH'
        timeframe : Requested bar frequency
        start     : Range start (UTC, timezone-aware)
        end       : Range end   (UTC, timezone-aware)

        Returns
        -------
        List of `MarketBar` with adj_type=NONE (raw / unadjusted).
        List may be empty if no data exists for the range.

        Raises
        ------
        DataSourceUnavailableError
        DataSourceRateLimitError
        DataSourceSchemaChangedError
        """

    # ------------------------------------------------------------------ #
    # Adjustment events (corporate actions)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def fetch_adjustment_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[AdjustmentEvent]:
        """
        Return ex-dividend / split events for `symbol` in [start, end].

        Returns an empty list if no events exist or the adapter does not
        support corporate-action data for the given symbol.
        """
