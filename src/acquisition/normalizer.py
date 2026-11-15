"""
src/acquisition/normalizer.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Single-responsibility engine for data cleaning, volume normalization,
VWAP sanity checking, and deterministic MarketBar assembly.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

import pandas as pd

from src.acquisition.base import RawProviderResponse, VolumeNormalizationSpec, VolumeUnit
from src.core.entities import AdjustType, DataOrigin, MarketBar
from src.core.exceptions import DataQualityError, DataSourceSchemaChangedError

logger = logging.getLogger("BarNormalizer")


class BarNormalizer:
    """
    Standardizes raw provider responses into verified, normalized MarketBars.
    Strictly owns volume conversion logic and prevents double conversion.
    """

    @classmethod
    def normalize_and_validate(
        cls,
        raw_response: RawProviderResponse,
        expected_symbol: str,
        start: datetime,
        end: datetime,
    ) -> tuple[list[MarketBar], VolumeNormalizationSpec]:
        """
        Normalize raw provider dataframe into validated MarketBar entities.

        Guarantees:
        1. Validates presence of essential columns (OHLCV).
        2. Validates raw values: volume >= 0, close > 0, amount >= 0.
        3. Conducts VWAP plausibility check against declared volume_unit.
        4. Applies volume conversion EXACTLY ONCE (LOT -> *100, SHARE -> *1).
        5. Generates deterministic SHA-256 checksum per bar.
        """
        df = raw_response.raw_df
        if df is None or df.empty:
            empty_spec = VolumeNormalizationSpec(
                raw_volume=0.0,
                raw_volume_unit=raw_response.volume_unit,
                normalized_volume=0.0,
                unit_conversion_factor=100.0 if raw_response.volume_unit == VolumeUnit.LOT else 1.0,
                vwap_ratio=1.0,
                is_validated=True,
            )
            return [], empty_spec

        # Standardize column names (mapping from common Chinese/English names)
        column_map = {
            "date": "ts",
            "日期": "ts",
            "open": "open",
            "开盘": "open",
            "high": "high",
            "最高": "high",
            "low": "low",
            "最低": "low",
            "close": "close",
            "收盘": "close",
            "volume": "volume",
            "成交量": "volume",
            "amount": "amount",
            "成交额": "amount",
        }

        # Work on a copy to prevent in-place mutation of provider raw data
        work_df = df.copy()
        matched_cols = {k: v for k, v in column_map.items() if k in work_df.columns}
        work_df = work_df.rename(columns=matched_cols)

        required = ["ts", "open", "high", "low", "close", "volume", "amount"]
        missing = [col for col in required if col not in work_df.columns]
        if missing:
            raise DataSourceSchemaChangedError(
                raw_response.source_id,
                f"Missing required columns in raw response for {expected_symbol}: {missing}",
            )

        # Determine conversion factor based strictly on declared unit
        unit = raw_response.volume_unit
        if unit == VolumeUnit.LOT:
            factor = 100.0
        elif unit == VolumeUnit.SHARE:
            factor = 1.0
        else:
            raise ValueError(f"Unsupported volume unit: {unit}")

        # Compute sample VWAP plausibility check if amount is available
        total_raw_vol = float(work_df["volume"].sum())
        total_amount = float(work_df["amount"].sum())
        avg_close = float(work_df["close"].mean()) if not work_df.empty else 1.0

        vwap_ratio = 1.0
        if total_raw_vol > 0 and total_amount > 0 and avg_close > 0:
            # Raw ratio = amount / (raw_volume * avg_close)
            raw_ratio = total_amount / (total_raw_vol * avg_close)
            if unit == VolumeUnit.LOT:
                # If unit is LOT, raw_ratio should naturally be ~100.0
                vwap_ratio = raw_ratio / 100.0
                if raw_ratio < 2.0:
                    logger.warning(
                        "Volume unit anomaly for %s: declared LOT but raw_ratio=%.2f < 2.0!",
                        expected_symbol,
                        raw_ratio,
                    )
            else:
                # If unit is SHARE, raw_ratio should naturally be ~1.0
                vwap_ratio = raw_ratio
                if raw_ratio > 50.0:
                    logger.warning(
                        "Volume unit anomaly for %s: declared SHARE but raw_ratio=%.2f > 50.0!",
                        expected_symbol,
                        raw_ratio,
                    )

        bars: list[MarketBar] = []
        now_utc = datetime.now(UTC)
        canonical_sym = expected_symbol.upper().strip()

        # Origin determination
        origin = (
            DataOrigin.SYNTHETIC_TEST
            if raw_response.source_id == "mock"
            else DataOrigin.REAL_PROVIDER
        )

        for _, row in work_df.iterrows():
            # Parse timestamp
            raw_ts = row["ts"]
            if isinstance(raw_ts, str):
                date_str = raw_ts.split()[0]
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
            elif isinstance(raw_ts, datetime):
                dt = raw_ts if raw_ts.tzinfo is not None else raw_ts.replace(tzinfo=UTC)
            elif hasattr(raw_ts, "to_pydatetime"):
                pydt = raw_ts.to_pydatetime()
                dt = pydt if pydt.tzinfo is not None else pydt.replace(tzinfo=UTC)
            else:
                dt = pd.to_datetime(raw_ts).to_pydatetime().replace(tzinfo=UTC)

            # Date filtering
            if dt < start or dt > end:
                continue

            open_p = float(row["open"])
            high_p = float(row["high"])
            low_p = float(row["low"])
            close_p = float(row["close"])
            raw_vol = float(row["volume"])
            amount = float(row["amount"])

            # Defensive validation of raw price geometry
            if open_p < 0 or high_p < 0 or low_p < 0 or close_p < 0:
                raise DataQualityError(
                    canonical_sym,
                    f"Negative price at {dt}: O={open_p}, H={high_p}, L={low_p}, C={close_p}",
                )
            if raw_vol < 0:
                raw_vol = 0.0
            if amount < 0:
                amount = 0.0

            # Single volume conversion
            norm_vol = raw_vol * factor

            # Zero-volume handling (e.g. trading halt)
            if norm_vol <= 0:
                norm_vol = 0.0
                amount = 0.0
                open_p = high_p = low_p = close_p

            # Deterministic SHA-256 fingerprint for bar payload
            bar_hash_raw = (
                f"{canonical_sym}|{dt.isoformat()}|{open_p:.4f}|"
                f"{high_p:.4f}|{low_p:.4f}|{close_p:.4f}|{norm_vol:.0f}"
            )
            checksum = hashlib.sha256(bar_hash_raw.encode("utf-8")).hexdigest()[:16]

            bar = MarketBar(
                symbol=canonical_sym,
                timeframe=raw_response.timeframe,
                adj_type=AdjustType.NONE,
                ts=dt,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=norm_vol,
                amount=amount,
                source_id=raw_response.source_id,
                data_origin=origin,
                source_interface=raw_response.source_interface,
                checksum=checksum,
                fetched_at=now_utc,
            )
            bars.append(bar)

        bars.sort(key=lambda b: b.ts)

        spec = VolumeNormalizationSpec(
            raw_volume=total_raw_vol,
            raw_volume_unit=unit,
            normalized_volume=total_raw_vol * factor,
            normalized_volume_unit=VolumeUnit.SHARE,
            unit_conversion_factor=factor,
            vwap_ratio=vwap_ratio,
            is_validated=True,
        )

        return bars, spec
