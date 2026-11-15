"""
src/acquisition/service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Unified Data Acquisition Service orchestrating:
1. Provider selection and failover routing
2. Raw data fetching (Single Responsibility)
3. Volume normalization and Bar validation (Single Responsibility)
4. Raw response gzip archival & SHA-256 provenance tracking
5. Atomic persistence to CompositeStorageEngine (Parquet + SQLite metadata)
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path

from src.acquisition.base import (
    BaseProvider,
    RawProviderResponse,
    VolumeNormalizationSpec,
)
from src.acquisition.normalizer import BarNormalizer
from src.acquisition.providers.akshare_provider import normalize_symbol_parts
from src.acquisition.registry import ProviderRegistry
from src.core.entities import (
    Market,
    MarketBar,
    RawResponseArchive,
    Timeframe,
)
from src.core.exceptions import (
    DataSourceUnavailableError,
    StorageError,
)
from src.storage.composite_engine import CompositeStorageEngine

logger = logging.getLogger("AcquisitionService")


def infer_market_from_symbol(symbol: str) -> Market:
    """Infer target Market enum from canonical symbol."""
    _, ex = normalize_symbol_parts(symbol)
    if ex in ("SH", "SZ", "BJ"):
        return Market.CN_A
    if ex == "HK":
        return Market.CN_HK
    if ex == "INDEX" or symbol.upper().endswith(".INDEX"):
        return Market.INDEX
    return Market.CN_A


class AcquisitionService:
    """
    Coordinates end-to-end data acquisition pipelines between external providers
    and internal storage engines while upholding provenance and normalization contracts.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        storage: CompositeStorageEngine,
        raw_storage_dir: Path | None = None,
    ) -> None:
        self.registry = registry
        self.storage = storage
        self.raw_storage_dir = raw_storage_dir or (self.storage.data_root / "raw")

    async def acquire_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        provider_preference: str | None = None,
        save_to_storage: bool = True,
    ) -> tuple[list[MarketBar], VolumeNormalizationSpec, RawResponseArchive]:
        """
        Execute full acquisition pipeline for a single security symbol.
        """
        canonical_symbol = symbol.upper().strip()
        market = infer_market_from_symbol(canonical_symbol)

        # 1. Resolve providers
        providers_to_try: list[BaseProvider] = []
        if provider_preference and provider_preference != "auto":
            preferred = self.registry.get_provider(provider_preference)
            providers_to_try.append(preferred)
        else:
            market_providers = self.registry.get_providers_for_market(market)
            if not market_providers:
                # Fallback to all providers if none registered specifically for market
                providers_to_try = [
                    self.registry.get_provider(pid) for pid in self.registry.list_providers()
                ]
            else:
                providers_to_try = market_providers

        if not providers_to_try:
            raise DataSourceUnavailableError(
                "acquisition_service",
                f"No provider found for '{canonical_symbol}' in market '{market.value}'",
            )

        # 2. Fetch raw response with failover
        raw_resp: RawProviderResponse | None = None
        last_error: Exception | None = None

        for provider in providers_to_try:
            try:
                logger.info(
                    "Attempting raw bar fetch for %s via provider '%s'",
                    canonical_symbol,
                    provider.provider_id,
                )
                resp = await provider.fetch_raw_bars(
                    symbol=canonical_symbol,
                    timeframe=timeframe,
                    start=start,
                    end=end,
                )
                if resp.success:
                    raw_resp = resp
                    break
                else:
                    logger.warning(
                        "Provider '%s' returned empty or unsuccessful response for %s: %s",
                        provider.provider_id,
                        canonical_symbol,
                        resp.error_message,
                    )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Provider '%s' failed for %s: %s. Proceeding to failover if available.",
                    provider.provider_id,
                    canonical_symbol,
                    exc,
                )

        if raw_resp is None:
            err_msg = str(last_error) if last_error else "All providers returned empty response"
            raise DataSourceUnavailableError("acquisition_service", err_msg)

        # 3. Bar Normalization & Raw Value Validation (Single Responsibility)
        bars, volume_spec = BarNormalizer.normalize_and_validate(
            raw_response=raw_resp,
            expected_symbol=canonical_symbol,
            start=start,
            end=end,
        )

        # 4. Raw Response Archival & Hash Provenance
        archive_rec = await self._archive_raw_response(
            raw_resp=raw_resp,
            bars=bars,
            market=market,
            start=start,
            end=end,
        )

        # 5. Persist to CompositeStorageEngine (Atomic Parquet + Coverage Metadata)
        if save_to_storage and bars:
            try:
                await self.storage.write_bars(bars)
            except Exception as write_err:
                logger.error(
                    "Failed to commit bars for %s to storage: %s", canonical_symbol, write_err
                )
                raise StorageError(f"Could not persist bars to storage: {write_err}") from write_err

        return bars, volume_spec, archive_rec

    async def _archive_raw_response(
        self,
        raw_resp: RawProviderResponse,
        bars: list[MarketBar],
        market: Market,
        start: datetime,
        end: datetime,
    ) -> RawResponseArchive:
        """Compress raw response, compute dual SHA-256 hashes, and persist audit record."""
        payload_text = raw_resp.raw_payload_text or ""
        raw_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
        norm_hash = (
            hashlib.sha256("|".join(b.checksum for b in bars).encode("utf-8")).hexdigest()
            if bars
            else "empty"
        )

        raw_payload_path_str = ""
        if payload_text and self.raw_storage_dir:
            try:
                day_str = raw_resp.request_ts.strftime("%Y%m%d")
                target_dir = self.raw_storage_dir / raw_resp.source_id / day_str
                target_dir.mkdir(parents=True, exist_ok=True)

                safe_iface = raw_resp.source_interface.replace(":", "_").replace("/", "_")
                ts_ms = int(time.time() * 1000)
                gz_file = target_dir / f"{raw_resp.symbol}_{safe_iface}_{ts_ms}.json.gz"

                with gzip.open(gz_file, "wt", encoding="utf-8") as gz:
                    gz.write(payload_text)

                raw_payload_path_str = str(gz_file)
            except Exception as gz_err:
                logger.warning("Could not persist compressed raw payload: %s", gz_err)

        archive = RawResponseArchive(
            provider_name=raw_resp.source_id,
            source_interface=raw_resp.source_interface,
            request_ts=raw_resp.request_ts,
            request_params={
                "symbol": raw_resp.symbol,
                "timeframe": raw_resp.timeframe.value,
                "start": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
            },
            response_status="OK" if raw_resp.success else "EMPTY",
            response_ts=raw_resp.response_ts,
            raw_response_hash=raw_hash,
            normalized_data_hash=norm_hash,
            symbol=raw_resp.symbol,
            market=market,
            row_count=len(bars),
            raw_payload_path=raw_payload_path_str,
            transformation_version="v2.0-normalized",
        )

        # Persist audit record in SQLite
        try:
            await self.storage.sqlite.insert_raw_response_archive(archive)
        except Exception as audit_err:
            logger.warning("Failed to record raw_response_audit in SQLite: %s", audit_err)

        return archive
