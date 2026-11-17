"""
src/acquisition/providers/akshare_provider.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AKShare data provider implementation adhering to single-responsibility principle:
retrieves raw market payloads without performing normalization or cleaning.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from src.acquisition.base import BaseProvider, RawProviderResponse, VolumeUnit
from src.core.entities import AssetType, ListingStatus, Market, Security, Timeframe
from src.core.exceptions import (
    DataSourceRateLimitError,
    DataSourceSchemaChangedError,
    DataSourceUnavailableError,
)

logger = logging.getLogger("AKShareProvider")


def normalize_symbol_parts(symbol: str) -> tuple[str, str]:
    """Split canonical symbol into (code, market_or_exchange)."""
    clean = symbol.upper().strip()
    if "." in clean:
        parts = clean.split(".", 1)
        return parts[0], parts[1]

    if re.match(r"^6\d{5}$", clean):
        return clean, "SH"
    if re.match(r"^(00|30)\d{4}$", clean):
        return clean, "SZ"
    if re.match(r"^(4|8|92)\d{4,5}$", clean):
        return clean, "BJ"
    if re.match(r"^\d{5}$", clean):
        return clean, "HK"
    return clean, ""


class AsyncRateLimiter:
    """Token-bucket / minimum-interval rate limiter."""

    def __init__(self, requests_per_second: float = 3.0) -> None:
        self.min_interval = 1.0 / max(requests_per_second, 0.1)
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()


class AKShareProvider(BaseProvider):
    """
    AKShare market data provider.
    Focuses exclusively on fetching raw responses from external endpoints.
    """

    def __init__(
        self,
        requests_per_second: float = 2.0,
        max_retries: int = 3,
        request_timeout: float = 15.0,
        cooling_seconds: float = 60.0,
    ) -> None:
        self._rate_limiter = AsyncRateLimiter(requests_per_second)
        self._max_retries = max_retries
        self._timeout = request_timeout
        self._cooling_seconds = cooling_seconds
        self._cooling_until: float = 0.0

    @property
    def provider_id(self) -> str:
        return "akshare"

    @property
    def supported_markets(self) -> list[Market]:
        return [Market.CN_A, Market.CN_HK, Market.INDEX]

    @property
    def supported_timeframes(self) -> list[Timeframe]:
        return [Timeframe.D1]

    async def _execute_with_retry(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a blocking AKShare call with rate limiting, timeouts, and retries."""
        now = time.monotonic()
        if now < self._cooling_until:
            wait_rem = self._cooling_until - now
            raise DataSourceRateLimitError(
                self.provider_id,
                retry_after=wait_rem,
            )

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                loop = asyncio.get_running_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: func(*args, **kwargs)),
                    timeout=self._timeout,
                )
            except TimeoutError as te:
                last_error = te
                logger.warning(
                    "AKShare call %s timed out (attempt %d/%d)",
                    getattr(func, "__name__", str(func)),
                    attempt,
                    self._max_retries,
                )
            except Exception as e:
                last_error = e
                err_msg = str(e)
                if "429" in err_msg or "Too Many Requests" in err_msg:
                    self._cooling_until = time.monotonic() + self._cooling_seconds
                    raise DataSourceRateLimitError(
                        self.provider_id, retry_after=self._cooling_seconds
                    ) from e
                if "临时限流" in err_msg or "断开了连接" in err_msg:
                    raise DataSourceUnavailableError(self.provider_id, err_msg) from e
                logger.warning(
                    "AKShare call %s failed (attempt %d/%d): %s",
                    getattr(func, "__name__", str(func)),
                    attempt,
                    self._max_retries,
                    e,
                )

            if attempt < self._max_retries:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

        raw_err = str(last_error) if last_error else "Max retries exceeded"
        if isinstance(last_error, (ConnectionError, TimeoutError, OSError)):
            raise DataSourceUnavailableError(self.provider_id, raw_err) from last_error
        raise DataSourceUnavailableError(self.provider_id, raw_err)

    async def check_health(self) -> bool:
        """Lightweight connectivity probe."""
        try:
            import akshare as ak

            check_fn = getattr(
                ak, "calendar_trade_date_hist_sina", getattr(ak, "tool_trade_date_hist_sina", None)
            )
            if check_fn is None:
                return False
            df = await self._execute_with_retry(check_fn)
            return df is not None and not df.empty
        except Exception as exc:
            logger.warning("AKShare health check failed: %s", exc)
            return False

    async def fetch_security_list(self, market: Market) -> list[Security]:
        """Fetch active securities list for given market."""
        if market not in self.supported_markets:
            raise ValueError(f"Market '{market}' is not supported by {self.provider_id}")

        import akshare as ak

        securities: list[Security] = []

        if market == Market.CN_A:
            df = await self._execute_with_retry(ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return []
            for _, row in df.iterrows():
                code = str(row["代码"]).strip().zfill(6)
                name = str(row["名称"]).strip()
                _, ex = normalize_symbol_parts(code)
                canonical_symbol = f"{code}.{ex}" if ex else code
                securities.append(
                    Security(
                        symbol=canonical_symbol,
                        name=name,
                        market=Market.CN_A,
                        asset_type=AssetType.STOCK,
                        listing_status=ListingStatus.LISTED,
                        currency="CNY",
                    )
                )

        elif market == Market.CN_HK:
            df = await self._execute_with_retry(ak.stock_hk_spot_em)
            if df is None or df.empty:
                return []
            for _, row in df.iterrows():
                code = str(row["代码"]).strip()
                name = str(row["名称"]).strip()
                securities.append(
                    Security(
                        symbol=f"{code}.HK",
                        name=name,
                        market=Market.CN_HK,
                        asset_type=AssetType.STOCK,
                        listing_status=ListingStatus.LISTED,
                        currency="HKD",
                    )
                )

        elif market == Market.INDEX:
            df = await self._execute_with_retry(ak.stock_zh_index_spot_em)
            if df is None or df.empty:
                return []
            for _, row in df.iterrows():
                code = str(row["代码"]).strip()
                name = str(row["名称"]).strip()
                _, ex = normalize_symbol_parts(code)
                canonical_symbol = f"{code}.{ex}" if ex else f"{code}.INDEX"
                securities.append(
                    Security(
                        symbol=canonical_symbol,
                        name=name,
                        market=Market.INDEX,
                        asset_type=AssetType.INDEX,
                        listing_status=ListingStatus.LISTED,
                        currency="CNY",
                    )
                )

        return securities

    async def fetch_raw_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> RawProviderResponse:
        """
        Fetch raw bar data from AKShare without performing normalization.
        Declares exact raw VolumeUnit for BarNormalizer processing.
        """
        if timeframe != Timeframe.D1:
            raise ValueError(f"Timeframe '{timeframe}' is not supported by AKShareProvider")

        import akshare as ak

        code, exchange = normalize_symbol_parts(symbol)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        t0 = time.perf_counter()
        req_ts = datetime.now(UTC)

        source_interface = ""
        volume_unit = VolumeUnit.SHARE
        df: pd.DataFrame | None = None

        if exchange == "HK":
            source_interface = "akshare:stock_hk_hist"
            # EastMoney HK returns volume in individual shares
            volume_unit = VolumeUnit.SHARE
            df = await self._execute_with_retry(
                ak.stock_hk_hist,
                symbol=code,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="",
            )
        elif exchange == "INDEX" or symbol.endswith(".INDEX"):
            source_interface = "akshare:index_zh_a_hist"
            # EastMoney A-share index returns volume in hands/lots
            volume_unit = VolumeUnit.LOT
            df = await self._execute_with_retry(
                ak.index_zh_a_hist,
                symbol=code,
                period="daily",
                start_date=start_str,
                end_date=end_str,
            )
        else:
            # A-Share: Try EastMoney primary first; on outage/limit failover to Sina daily
            em_fn = getattr(ak, "stock_zh_a_hist_em", getattr(ak, "stock_zh_a_hist", None))
            sina_fn = getattr(ak, "stock_zh_a_hist_sina", getattr(ak, "stock_zh_a_daily", None))
            try:
                source_interface = "akshare:stock_zh_a_hist"
                # EastMoney stock_zh_a_hist returns volume in LOTS (手)
                volume_unit = VolumeUnit.LOT
                if em_fn is None:
                    raise DataSourceUnavailableError(self.provider_id, "EastMoney hist function not found")
                df = await self._execute_with_retry(
                    em_fn,
                    symbol=code,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust="",
                )
            except (DataSourceUnavailableError, Exception) as em_err:
                if isinstance(em_err, (DataSourceSchemaChangedError, DataSourceRateLimitError)):
                    raise

                logger.warning(
                    "Primary EastMoney 'stock_zh_a_hist' unavailable for %s (%s). "
                    "Attempting secondary failover to Sina 'stock_zh_a_daily'",
                    symbol,
                    em_err,
                )
                self._cooling_until = 0.0
                source_interface = "akshare:stock_zh_a_daily"
                # Sina stock_zh_a_daily returns volume in SHARES (股)
                volume_unit = VolumeUnit.SHARE
                is_sh = exchange == "SH" or code.startswith("6")
                sina_code = f"sh{code}" if is_sh else f"sz{code}"
                if sina_fn is None:
                    raise DataSourceUnavailableError(self.provider_id, "Sina hist function not found")
                df = await self._execute_with_retry(
                    sina_fn,
                    symbol=sina_code,
                    adjust="",
                )

        t1 = time.perf_counter()
        resp_ts = datetime.now(UTC)
        latency = (t1 - t0) * 1000.0

        if df is None:
            df = pd.DataFrame()

        raw_payload = df.to_json(orient="split", date_format="iso") if not df.empty else ""

        return RawProviderResponse(
            symbol=symbol.upper().strip(),
            timeframe=timeframe,
            raw_df=df,
            raw_payload_text=raw_payload,
            source_id=self.provider_id,
            source_interface=source_interface,
            volume_unit=volume_unit,
            request_ts=req_ts,
            response_ts=resp_ts,
            latency_ms=latency,
            success=not df.empty,
            metadata={"row_count": len(df)},
        )
