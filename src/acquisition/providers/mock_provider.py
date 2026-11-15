"""
src/acquisition/providers/mock_provider.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deterministic mock provider for offline testing and boundary verification.
Strictly isolated from production execution.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pandas as pd

from src.acquisition.base import BaseProvider, RawProviderResponse, VolumeUnit
from src.core.entities import AssetType, ListingStatus, Market, Security, Timeframe


class MockProvider(BaseProvider):
    """
    Mock data provider generating deterministic synthetic data for unit testing.
    """

    def __init__(
        self,
        simulated_latency_ms: float = 1.0,
        should_fail: bool = False,
        volume_unit: VolumeUnit = VolumeUnit.SHARE,
    ) -> None:
        self._latency_ms = simulated_latency_ms
        self._should_fail = should_fail
        self._volume_unit = volume_unit

    @property
    def provider_id(self) -> str:
        return "mock"

    @property
    def supported_markets(self) -> list[Market]:
        return [Market.CN_A, Market.CN_HK, Market.INDEX]

    @property
    def supported_timeframes(self) -> list[Timeframe]:
        return [Timeframe.D1, Timeframe.H1, Timeframe.M5]

    async def check_health(self) -> bool:
        return not self._should_fail

    async def fetch_security_list(self, market: Market) -> list[Security]:
        if self._should_fail:
            raise RuntimeError("Mock provider simulated security list failure")

        if market == Market.CN_A:
            return [
                Security(
                    symbol="600519.SH",
                    name="贵州茅台",
                    market=Market.CN_A,
                    asset_type=AssetType.STOCK,
                    listing_status=ListingStatus.LISTED,
                    currency="CNY",
                ),
                Security(
                    symbol="000858.SZ",
                    name="五粮液",
                    market=Market.CN_A,
                    asset_type=AssetType.STOCK,
                    listing_status=ListingStatus.LISTED,
                    currency="CNY",
                ),
            ]
        elif market == Market.CN_HK:
            return [
                Security(
                    symbol="00700.HK",
                    name="腾讯控股",
                    market=Market.CN_HK,
                    asset_type=AssetType.STOCK,
                    listing_status=ListingStatus.LISTED,
                    currency="HKD",
                ),
            ]
        elif market == Market.INDEX:
            return [
                Security(
                    symbol="000300.SH",
                    name="沪深300",
                    market=Market.INDEX,
                    asset_type=AssetType.INDEX,
                    listing_status=ListingStatus.LISTED,
                    currency="CNY",
                ),
            ]
        return []

    async def fetch_raw_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> RawProviderResponse:
        req_ts = datetime.now(UTC)
        t0 = time.perf_counter()

        if self._should_fail:
            resp_ts = datetime.now(UTC)
            return RawProviderResponse(
                symbol=symbol,
                timeframe=timeframe,
                raw_df=pd.DataFrame(),
                raw_payload_text="",
                source_id=self.provider_id,
                source_interface="mock:failure",
                volume_unit=self._volume_unit,
                request_ts=req_ts,
                response_ts=resp_ts,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                success=False,
                error_message="Mock provider simulated fetch failure",
            )

        # Generate deterministic synthetic dataframe
        days_span = max((end - start).days, 1)
        records = []
        base_price = 1000.0 if "600519" in symbol else 100.0

        for i in range(min(days_span, 50)):
            curr_date = start + timedelta(days=i)
            if curr_date.weekday() in (5, 6):
                continue
            p = base_price + (i % 7) * 2.5
            vol = 50000.0 if self._volume_unit == VolumeUnit.SHARE else 500.0
            amt = vol * p if self._volume_unit == VolumeUnit.SHARE else (vol * 100.0) * p

            records.append(
                {
                    "ts": curr_date.strftime("%Y-%m-%d"),
                    "open": p,
                    "high": p * 1.02,
                    "low": p * 0.98,
                    "close": p * 1.01,
                    "volume": vol,
                    "amount": amt,
                }
            )

        df = pd.DataFrame(records)
        resp_ts = datetime.now(UTC)

        return RawProviderResponse(
            symbol=symbol,
            timeframe=timeframe,
            raw_df=df,
            raw_payload_text=df.to_json(orient="split", date_format="iso"),
            source_id=self.provider_id,
            source_interface="mock:synthetic_kline",
            volume_unit=self._volume_unit,
            request_ts=req_ts,
            response_ts=resp_ts,
            latency_ms=(time.perf_counter() - t0) * 1000.0 + self._latency_ms,
            success=not df.empty,
            metadata={"generated_rows": len(df)},
        )
