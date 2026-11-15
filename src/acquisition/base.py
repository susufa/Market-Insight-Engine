"""
src/acquisition/base.py
~~~~~~~~~~~~~~~~~~~~~~~
Core abstractions, contracts, and data structures for modular data acquisition.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import pandas as pd

from src.core.entities import Market, Security, Timeframe


class VolumeUnit(StrEnum):
    """Trading volume unit representation."""

    LOT = "lot"  # 1 lot = 100 shares in Chinese A-shares
    SHARE = "share"  # 1 individual share


@dataclass(frozen=True)
class VolumeNormalizationSpec:
    """
    Metadata recording exact volume conversion details and validation state.
    """

    raw_volume: float
    raw_volume_unit: VolumeUnit
    normalized_volume: float
    normalized_volume_unit: VolumeUnit = VolumeUnit.SHARE
    unit_conversion_factor: float = 1.0
    vwap_ratio: float = 1.0
    is_validated: bool = True


@dataclass
class RawProviderResponse:
    """
    Immutable raw response payload returned strictly by a BaseProvider.
    A provider is ONLY responsible for retrieving this raw payload;
    it must NOT perform normalization, cleaning, or business logic.
    """

    symbol: str
    timeframe: Timeframe
    raw_df: pd.DataFrame
    raw_payload_text: str
    source_id: str
    source_interface: str
    volume_unit: VolumeUnit
    request_ts: datetime
    response_ts: datetime
    latency_ms: float
    success: bool
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """
    Abstract interface contract for all external and internal market data providers.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g. 'akshare', 'baostock', 'mock')."""
        pass

    @property
    @abstractmethod
    def supported_markets(self) -> list[Market]:
        """List of supported market segments."""
        pass

    @property
    @abstractmethod
    def supported_timeframes(self) -> list[Timeframe]:
        """List of supported timeframes."""
        pass

    @abstractmethod
    async def fetch_raw_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> RawProviderResponse:
        """
        Fetch raw bar data for symbol over [start, end].
        Must return RawProviderResponse without applying volume normalization.
        """
        pass

    @abstractmethod
    async def fetch_security_list(self, market: Market) -> list[Security]:
        """Fetch active securities list for given market."""
        pass

    @abstractmethod
    async def check_health(self) -> bool:
        """Lightweight connectivity probe."""
        pass
