"""
adapters/akshare_adapter.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Concrete implementation of BaseDataSourceAdapter using AKShare.

Provides data fetching for China A-shares (CN_A), Hong Kong shares (CN_HK),
and major Chinese equity indices (INDEX).

Features:
- Thread-pool offloading for synchronous AKShare calls (asyncio.to_thread).
- Token-bucket / interval rate limiting to avoid upstream blocking.
- Exponential backoff with jitter on transient network/HTTP failures.
- Strict mapping to canonical domain entities (Security, MarketBar, AdjustmentEvent).
- Categorised exception mapping (DataSourceUnavailableError,
  DataSourceRateLimitError, DataSourceSchemaChangedError).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from core.entities import (
    AdjustmentEvent,
    AdjustType,
    AssetType,
    DataOrigin,
    ListingStatus,
    Market,
    MarketBar,
    RawResponseArchive,
    Security,
    Timeframe,
)
from core.exceptions import (
    DataSourceRateLimitError,
    DataSourceSchemaChangedError,
    DataSourceUnavailableError,
)
from core.interfaces.data_source import BaseDataSourceAdapter

logger = logging.getLogger(__name__)


class AsyncRateLimiter:
    """Token-bucket / minimum-interval rate limiter for async execution."""

    def __init__(self, requests_per_second: float = 5.0) -> None:
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


def normalize_symbol_parts(symbol: str) -> tuple[str, str]:
    """
    Split a canonical symbol into (code, market_or_exchange).

    Examples:
    - '600519.SH' -> ('600519', 'SH')
    - '000001.SZ' -> ('000001', 'SZ')
    - '00700.HK'  -> ('00700', 'HK')
    - '600519'    -> ('600519', 'SH') (inferred)
    """
    clean = symbol.upper().strip()
    if "." in clean:
        parts = clean.split(".", 1)
        return parts[0], parts[1]

    # Inferred exchange if symbol has no suffix
    if re.match(r"^6\d{5}$", clean):
        return clean, "SH"
    if re.match(r"^(00|30)\d{4}$", clean):
        return clean, "SZ"
    if re.match(r"^(4|8|92)\d{4,5}$", clean):
        return clean, "BJ"
    if re.match(r"^\d{5}$", clean):
        return clean, "HK"
    return clean, ""


class AKShareAdapter(BaseDataSourceAdapter):
    """
    Data source adapter integrating AKShare with Market Insight Engine.
    """

    def __init__(
        self,
        requests_per_second: float = 2.0,
        max_retries: int = 3,
        request_timeout: float = 15.0,
        cooling_seconds: float = 60.0,
        raw_storage_dir: Path | None = None,
    ) -> None:
        self._requests_per_second = requests_per_second
        self._max_retries = max_retries
        self._timeout = request_timeout
        self._cooling_seconds = cooling_seconds
        self._cooling_until: float = 0.0
        self._limiter = AsyncRateLimiter(requests_per_second)
        self.raw_storage_dir = raw_storage_dir
        self.last_raw_archive: RawResponseArchive | None = None

    # ------------------------------------------------------------------ #
    # Metadata Properties
    # ------------------------------------------------------------------ #

    @property
    def source_id(self) -> str:
        return "akshare"

    @property
    def supported_markets(self) -> list[Market]:
        return [Market.CN_A, Market.CN_HK, Market.INDEX]

    @property
    def supported_timeframes(self) -> list[Timeframe]:
        return [Timeframe.D1]

    # ------------------------------------------------------------------ #
    # Resilience & Execution Helper
    # ------------------------------------------------------------------ #

    async def _execute_with_retry(
        self,
        func: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute a synchronous blocking data function in a background thread
        with rate limiting, cooling-off circuit breaker, timeout, and exponential backoff retry.
        """
        now = time.monotonic()
        if now < self._cooling_until:
            remaining = self._cooling_until - now
            raise DataSourceRateLimitError(self.source_id, retry_after=remaining)

        await self._limiter.acquire()

        async def _call() -> Any:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(func, *args, **kwargs),
                    timeout=self._timeout,
                )
            except TimeoutError as exc:
                raise TimeoutError(f"AKShare call timed out after {self._timeout}s") from exc

        retryer = AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_random_exponential(multiplier=0.5, max=4.0),
            retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
            reraise=True,
        )

        try:
            async for attempt in retryer:
                with attempt:
                    return await _call()
        except Exception as e:
            raw_err = str(e)
            msg = raw_err.lower()
            if "429" in msg or "rate limit" in msg or "too many requests" in msg:
                self._cooling_until = time.monotonic() + self._cooling_seconds
                raise DataSourceRateLimitError(
                    self.source_id, retry_after=self._cooling_seconds
                ) from e
            if (
                "临时限流" in raw_err
                or "断开了连接" in raw_err
                or isinstance(e, (ConnectionError, TimeoutError, OSError))
            ):
                raise DataSourceUnavailableError(self.source_id, raw_err) from e
            # Pass through other exceptions (e.g. KeyError, ValueError, Schema errors)
            raise

    # ------------------------------------------------------------------ #
    # Health Check
    # ------------------------------------------------------------------ #

    async def check_health(self) -> bool:
        """Lightweight connectivity check."""
        try:
            import akshare as ak

            # Try a lightweight query
            df = await self._execute_with_retry(
                ak.tool_trade_date_hist_sina,
            )
            return df is not None and not df.empty
        except Exception as exc:
            logger.warning("AKShare health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Security List Fetching
    # ------------------------------------------------------------------ #

    async def fetch_security_list(self, market: Market) -> list[Security]:
        """Fetch list of active securities for a supported market."""
        if market not in self.supported_markets:
            raise ValueError(f"Market '{market}' is not supported by {self.source_id}")

        import akshare as ak

        securities: list[Security] = []
        try:
            if market == Market.CN_A:
                df: pd.DataFrame = await self._execute_with_retry(ak.stock_zh_a_spot_em)
                if df is None or df.empty:
                    return []
                # Required columns: 代码, 名称
                if "代码" not in df.columns or "名称" not in df.columns:
                    raise DataSourceSchemaChangedError(
                        self.source_id,
                        f"Missing expected columns in stock_zh_a_spot_em: {list(df.columns)}",
                    )
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
                if "代码" not in df.columns or "名称" not in df.columns:
                    raise DataSourceSchemaChangedError(
                        self.source_id,
                        f"Missing expected columns in stock_hk_spot_em: {list(df.columns)}",
                    )
                for _, row in df.iterrows():
                    code = str(row["代码"]).strip()
                    name = str(row["名称"]).strip()
                    canonical_symbol = f"{code}.HK"
                    securities.append(
                        Security(
                            symbol=canonical_symbol,
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
                if "代码" not in df.columns or "名称" not in df.columns:
                    raise DataSourceSchemaChangedError(
                        self.source_id,
                        f"Missing expected columns in stock_zh_index_spot_em: {list(df.columns)}",
                    )
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

        except (DataSourceRateLimitError, DataSourceUnavailableError, DataSourceSchemaChangedError):
            raise
        except Exception as e:
            raise DataSourceUnavailableError(self.source_id, str(e)) from e

    # ------------------------------------------------------------------ #
    # Historical Bar Data
    # ------------------------------------------------------------------ #

    async def fetch_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        """
        Fetch OHLCV bars for `symbol` over [start, end].
        Always returns raw / unadjusted bars (adj_type=NONE).
        """
        if timeframe != Timeframe.D1:
            raise ValueError(f"Timeframe '{timeframe}' is not natively supported by AKShareAdapter")

        import akshare as ak

        code, exchange = normalize_symbol_parts(symbol)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        request_ts = datetime.now(UTC)
        request_params = {
            "symbol": symbol,
            "timeframe": timeframe.value,
            "start": start_str,
            "end": end_str,
        }

        source_interface = ""
        df: pd.DataFrame | None = None

        try:
            if exchange == "HK":
                source_interface = "akshare:stock_hk_hist"
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
                df = await self._execute_with_retry(
                    ak.index_zh_a_hist,
                    symbol=code,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                )
            else:
                # Default to A-share: Try primary EastMoney; on outage/limit, failover to Sina daily
                try:
                    source_interface = "akshare:stock_zh_a_hist"
                    df = await self._execute_with_retry(
                        ak.stock_zh_a_hist,
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
                        "Primary A-share interface 'stock_zh_a_hist' unavailable for %s (%s). "
                        "Attempting secondary failover to Sina 'stock_zh_a_daily'",
                        symbol,
                        em_err,
                    )
                    # Reset cooling to allow secondary failover
                    self._cooling_until = 0.0
                    source_interface = "akshare:stock_zh_a_daily"
                    is_sh = exchange == "SH" or code.startswith("6")
                    sina_code = f"sh{code}" if is_sh else f"sz{code}"
                    df = await self._execute_with_retry(
                        ak.stock_zh_a_daily,
                        symbol=sina_code,
                        adjust="",
                    )

            if df is None or df.empty:
                self.last_raw_archive = RawResponseArchive(
                    provider_name=self.source_id,
                    source_interface=source_interface,
                    request_ts=request_ts,
                    request_params=request_params,
                    response_status="EMPTY",
                    response_ts=datetime.now(UTC),
                    raw_response_hash="empty",
                    normalized_data_hash="empty",
                    symbol=symbol.upper().strip(),
                    market=self._infer_market(symbol),
                    row_count=0,
                    raw_payload_path="",
                    transformation_version="v1.0",
                )
                return []

            # ---------------------------------------------------------- #
            # Raw Response Archival & Hashing (Step6 Provenance)
            # ---------------------------------------------------------- #
            raw_json_str = df.to_json(orient="split", date_format="iso")
            raw_hash = hashlib.sha256(raw_json_str.encode("utf-8")).hexdigest()
            raw_payload_path_str = ""
            if self.raw_storage_dir:
                try:
                    day_str = request_ts.strftime("%Y%m%d")
                    target_dir = self.raw_storage_dir / "akshare" / day_str
                    target_dir.mkdir(parents=True, exist_ok=True)
                    safe_iface = source_interface.replace(":", "_")
                    payload_file = (
                        target_dir
                        / f"{symbol.upper().strip()}_{safe_iface}_{int(time.time() * 1000)}.json"
                    )
                    payload_file.write_text(raw_json_str, encoding="utf-8")
                    raw_payload_path_str = str(payload_file)
                except Exception as save_err:
                    logger.warning("Could not persist raw payload file: %s", save_err)

            # Map column names if English (e.g. Sina)
            rename_map = {
                "date": "日期",
                "open": "开盘",
                "high": "最高",
                "low": "最低",
                "close": "收盘",
                "volume": "成交量",
                "amount": "成交额",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

            # Expected columns
            required_cols = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]
            for col in required_cols:
                if col not in df.columns:
                    raise DataSourceSchemaChangedError(
                        self.source_id,
                        f"Missing expected column '{col}' in historical bars for {symbol}",
                    )

            bars: list[MarketBar] = []
            now_utc = datetime.now(UTC)

            for _, row in df.iterrows():
                date_str = str(row["日期"]).split()[0]
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)

                # Filter within requested range
                if dt < start or dt > end:
                    continue

                open_p = float(row["开盘"])
                high_p = float(row["最高"])
                low_p = float(row["最低"])
                close_p = float(row["收盘"])
                volume = float(row["成交量"])
                amount = float(row["成交额"])

                # Handle zero-volume edge cases (e.g., halted trading sessions)
                # MarketBar requires: if volume == 0, amount == 0 and open == high == low == close
                if volume <= 0:
                    volume = 0.0
                    amount = 0.0
                    open_p = high_p = low_p = close_p

                # Deterministic SHA-256 fingerprint for bar payload
                bar_hash_raw = (
                    f"{symbol.upper().strip()}|{dt.isoformat()}|{open_p:.4f}|"
                    f"{high_p:.4f}|{low_p:.4f}|{close_p:.4f}|{volume:.0f}"
                )
                checksum = hashlib.sha256(bar_hash_raw.encode("utf-8")).hexdigest()[:16]

                bar = MarketBar(
                    symbol=symbol.upper().strip(),
                    timeframe=timeframe,
                    adj_type=AdjustType.NONE,
                    ts=dt,
                    open=open_p,
                    high=high_p,
                    low=low_p,
                    close=close_p,
                    volume=volume,
                    amount=amount,
                    source_id=self.source_id,
                    data_origin=DataOrigin.REAL_PROVIDER,
                    source_interface=source_interface,
                    checksum=checksum,
                    fetched_at=now_utc,
                )
                bars.append(bar)

            # Sort chronologically
            bars.sort(key=lambda b: b.ts)

            # ---------------------------------------------------------- #
            # Normalized Data Hashing & Archive Assembly (Step6 Provenance)
            # ---------------------------------------------------------- #
            norm_str = "|".join(b.checksum for b in bars)
            norm_hash = hashlib.sha256(norm_str.encode("utf-8")).hexdigest() if bars else "empty"

            self.last_raw_archive = RawResponseArchive(
                provider_name=self.source_id,
                source_interface=source_interface,
                request_ts=request_ts,
                request_params=request_params,
                response_status="SUCCESS" if bars else "EMPTY",
                response_ts=datetime.now(UTC),
                raw_response_hash=raw_hash,
                normalized_data_hash=norm_hash,
                symbol=symbol.upper().strip(),
                market=self._infer_market(symbol),
                row_count=len(bars),
                raw_payload_path=raw_payload_path_str,
                transformation_version="v1.0",
            )

            return bars

        except (DataSourceRateLimitError, DataSourceUnavailableError, DataSourceSchemaChangedError):
            raise
        except Exception as e:
            raise DataSourceUnavailableError(self.source_id, str(e)) from e

    async def fetch_bars_with_archive(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> tuple[list[MarketBar], RawResponseArchive | None]:
        """Fetch bars and return alongside the cryptographic raw response archive."""
        bars = await self.fetch_bars(symbol, timeframe, start, end)
        return bars, self.last_raw_archive

    @staticmethod
    def _infer_market(symbol: str) -> Market:
        clean = symbol.upper().strip()
        if clean.endswith((".SH", ".SZ", ".BJ")):
            return Market.CN_A
        if clean.endswith(".HK"):
            return Market.CN_HK
        if clean.endswith(".INDEX") or "INDEX" in clean:
            return Market.INDEX
        return Market.CN_A

    # ------------------------------------------------------------------ #
    # Corporate Actions (Adjustment Events)
    # ------------------------------------------------------------------ #

    async def fetch_adjustment_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[AdjustmentEvent]:
        """
        Fetch corporate dividend / split events for `symbol` in [start, end].
        """
        code, exchange = normalize_symbol_parts(symbol)
        if exchange == "HK" or exchange == "INDEX":
            return []

        import akshare as ak

        try:
            df: pd.DataFrame = await self._execute_with_retry(
                ak.stock_fhps_detail_em,
                symbol=code,
            )
            if df is None or df.empty:
                return []

            # Expected columns in stock_fhps_detail_em:
            # 除权除息日, 现金分红-现金分红比例, 送转股份-送转总比例
            date_col = None
            for candidate in ["除权除息日", "除权日", "股权登记日"]:
                if candidate in df.columns:
                    date_col = candidate
                    break

            if not date_col:
                return []

            events: list[AdjustmentEvent] = []
            for _, row in df.iterrows():
                val = row[date_col]
                if pd.isna(val) or not str(val).strip() or str(val).strip() == "--":
                    continue

                try:
                    ex_date = datetime.strptime(str(val).strip()[:10], "%Y-%m-%d").replace(
                        tzinfo=UTC
                    )
                except ValueError:
                    continue

                if ex_date < start or ex_date > end:
                    continue

                # Parse dividend
                cash_div = 0.0
                if "现金分红-现金分红比例" in df.columns and not pd.isna(
                    row["现金分红-现金分红比例"]
                ):
                    try:
                        # usually per 10 shares
                        val_str = str(row["现金分红-现金分红比例"]).replace("元", "")
                        cash_div = float(val_str) / 10.0
                    except (ValueError, TypeError):
                        cash_div = 0.0

                bonus_ratio = 0.0
                if "送转股份-送转总比例" in df.columns and not pd.isna(row["送转股份-送转总比例"]):
                    try:
                        # usually per 10 shares
                        val_str = str(row["送转股份-送转总比例"]).replace("股", "")
                        bonus_ratio = float(val_str) / 10.0
                    except (ValueError, TypeError):
                        bonus_ratio = 0.0

                event = AdjustmentEvent(
                    symbol=symbol.upper().strip(),
                    ex_date=ex_date,
                    cash_dividend=max(0.0, cash_div),
                    bonus_ratio=max(0.0, bonus_ratio),
                    rights_ratio=0.0,
                    rights_price=0.0,
                    source_id=self.source_id,
                )
                events.append(event)

            events.sort(key=lambda ev: ev.ex_date)
            return events

        except Exception as exc:
            logger.info("No adjustment events or error fetching for %s: %s", symbol, exc)
            return []
