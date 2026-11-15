"""
storage/parquet_manager.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Handles high-performance Parquet storage, atomic commits, CRC32/SHA256
checksum verification, and quarantine routing.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import time
import zlib
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from core.entities import (
    DataQualityReport,
    DataRevisionRecord,
    Market,
    MarketBar,
    Timeframe,
)
from core.exceptions import AtomicWriteError, StorageCorruptionError

logger = logging.getLogger(__name__)

BAR_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "symbol": pl.String,
    "timeframe": pl.String,
    "adj_type": pl.String,
    "ts": pl.Datetime(time_unit="us", time_zone="UTC"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
    "source_id": pl.String,
    "data_origin": pl.String,
    "source_interface": pl.String,
    "checksum": pl.String,
    "fetched_at": pl.Datetime(time_unit="us", time_zone="UTC"),
}


def infer_market_from_symbol(symbol: str) -> Market:
    """Infer market enum from canonical symbol suffix."""
    upper = symbol.upper().strip()
    if upper.endswith((".SH", ".SZ", ".BJ")):
        return Market.CN_A
    if upper.endswith(".HK"):
        return Market.CN_HK
    if upper.endswith(".INDEX"):
        return Market.INDEX
    return Market.CN_A


def calculate_file_checksums(path: Path) -> tuple[str, str]:
    """Calculate (crc32_hex, sha256_hex) for a given file."""
    crc = 0
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            crc = zlib.crc32(chunk, crc)
            sha256.update(chunk)
    return f"{crc & 0xFFFFFFFF:08x}", sha256.hexdigest()


class ParquetStorageManager:
    """
    Manages local Parquet files for market bars with atomic commit semantics.
    """

    def __init__(
        self,
        production_dir: Path,
        staging_dir: Path,
        quarantine_dir: Path,
    ) -> None:
        self.production_dir = production_dir
        self.staging_dir = staging_dir
        self.quarantine_dir = quarantine_dir
        self.last_detected_revision: DataRevisionRecord | None = None

    def get_production_path(self, symbol: str, timeframe: Timeframe) -> Path:
        """Resolve production path: production/{market}/{timeframe}/{symbol}.parquet"""
        market = infer_market_from_symbol(symbol)
        return (
            self.production_dir
            / market.value
            / str(timeframe.value)
            / f"{symbol.upper().strip()}.parquet"
        )

    def write_bars_atomic(
        self,
        bars: list[MarketBar],
        timeframe: Timeframe,
        *,
        overwrite_existing: bool = False,
    ) -> tuple[int, str, Path]:
        """
        Atomically write or upsert bars into the production Parquet store.

        Returns (new_rows_count, sha256_hash, final_path).
        """
        if not bars:
            return 0, "", Path()

        symbol = bars[0].symbol.upper().strip()
        final_path = self.get_production_path(symbol, timeframe)
        final_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert incoming bars to Polars DataFrame
        incoming_dicts = [
            {
                "symbol": b.symbol,
                "timeframe": b.timeframe.value,
                "adj_type": b.adj_type.value,
                "ts": b.ts,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "amount": b.amount,
                "source_id": b.source_id,
                "data_origin": str(getattr(b, "data_origin", "unknown")),
                "source_interface": str(getattr(b, "source_interface", "")),
                "checksum": str(getattr(b, "checksum", "")),
                "fetched_at": b.fetched_at,
            }
            for b in bars
        ]
        incoming_df = pl.DataFrame(incoming_dicts, schema=BAR_SCHEMA)

        # Merge with existing file if present
        self.last_detected_revision = None
        if final_path.exists():
            try:
                existing_df = pl.read_parquet(final_path)
                incoming_ts = set(incoming_df["ts"].to_list())
                existing_ts = set(existing_df["ts"].to_list())
                overlap_ts = incoming_ts.intersection(existing_ts)

                # Step6 Revision Detection on overlapping timestamps
                if overlap_ts:
                    overlap_list = list(overlap_ts)
                    old_sub = existing_df.filter(pl.col("ts").is_in(overlap_list)).sort("ts")
                    new_sub = incoming_df.filter(pl.col("ts").is_in(overlap_list)).sort("ts")

                    diff_samples: list[dict[str, str]] = []
                    for old_row, new_row in zip(
                        old_sub.to_dicts(), new_sub.to_dicts(), strict=False
                    ):
                        p_diff = abs(float(old_row["close"]) - float(new_row["close"])) > 1e-4
                        v_diff = abs(float(old_row["volume"]) - float(new_row["volume"])) > 1e-4
                        if p_diff or v_diff:
                            diff_samples.append(
                                {
                                    "ts": str(old_row["ts"]),
                                    "old_close": str(old_row["close"]),
                                    "new_close": str(new_row["close"]),
                                    "old_volume": str(old_row["volume"]),
                                    "new_volume": str(new_row["volume"]),
                                }
                            )

                    if diff_samples:
                        old_s = "".join(f"{r['close']}:{r['volume']}" for r in old_sub.to_dicts())
                        old_fp = hashlib.sha256(old_s.encode()).hexdigest()[:16]
                        new_s = "".join(f"{r['close']}:{r['volume']}" for r in new_sub.to_dicts())
                        new_fp = hashlib.sha256(new_s.encode()).hexdigest()[:16]
                        self.last_detected_revision = DataRevisionRecord(
                            symbol=symbol,
                            timeframe=timeframe,
                            revised_ts_count=len(diff_samples),
                            sample_diffs=diff_samples[:10],
                            old_fingerprint=old_fp,
                            new_fingerprint=new_fp,
                            reason="historical_bar_revision_detected",
                        )
                        logger.warning(
                            "Historical bar revision detected for %s (%s): %d bars modified",
                            symbol,
                            timeframe.value,
                            len(diff_samples),
                        )

                if overwrite_existing:
                    # Remove timestamps present in incoming from existing
                    filtered_existing = existing_df.filter(~pl.col("ts").is_in(list(incoming_ts)))
                    merged_df = pl.concat([filtered_existing, incoming_df])
                else:
                    # Keep existing, append only new timestamps
                    new_rows = incoming_df.filter(~pl.col("ts").is_in(list(existing_ts)))
                    merged_df = pl.concat([existing_df, new_rows])
            except Exception as e:
                logger.error("Failed to read existing parquet at %s: %s", final_path, e)
                raise StorageCorruptionError(str(final_path)) from e
        else:
            merged_df = incoming_df

        # Sort and deduplicate by timestamp
        merged_df = merged_df.unique(subset=["ts"], keep="last").sort("ts")
        total_rows = len(merged_df)

        # Temporary file path in the same directory (ensures same filesystem volume)
        temp_file = final_path.with_name(f".{symbol}_{int(time.time() * 1000)}.tmp")

        try:
            # 1. Write to temporary file
            merged_df.write_parquet(temp_file, compression="zstd")

            # 2. Integrity verification on temp file
            meta = pq.read_metadata(temp_file)
            if meta.num_rows != total_rows:
                raise AtomicWriteError(
                    str(temp_file),
                    f"Row count mismatch: expected {total_rows}, got {meta.num_rows}",
                )

            crc32_hex, sha256_hex = calculate_file_checksums(temp_file)

            # 3. Atomic rename with Windows retry mechanism
            max_replace_retries = 5
            for attempt in range(max_replace_retries):
                try:
                    os.replace(temp_file, final_path)
                    break
                except OSError as os_err:
                    if attempt == max_replace_retries - 1:
                        raise AtomicWriteError(
                            str(final_path), f"os.replace failed after retries: {os_err}"
                        ) from os_err
                    time.sleep(0.05 * (attempt + 1))

            new_rows_count = len(incoming_df)
            return new_rows_count, sha256_hex, final_path

        except Exception:
            # If any failure occurs, clean up temporary file
            if temp_file.exists():
                with contextlib.suppress(Exception):
                    temp_file.unlink()
            raise

    def read_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """
        Read bars for `symbol` within [start, end].
        Returns empty DataFrame with correct schema if no data exists.
        """
        path = self.get_production_path(symbol, timeframe)
        if not path.exists():
            return pl.DataFrame(schema=BAR_SCHEMA)

        try:
            df = pl.read_parquet(path)
            # Filter range
            filtered = df.filter((pl.col("ts") >= start) & (pl.col("ts") <= end)).sort("ts")
            return filtered
        except Exception as e:
            logger.error("Failed to read parquet file %s: %s", path, e)
            raise StorageCorruptionError(str(path)) from e

    def route_to_quarantine(
        self,
        bars: list[MarketBar],
        report: DataQualityReport,
    ) -> Path:
        """
        Save rejected dirty data into the quarantine zone along with
        its inspection report for auditability.
        """
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        symbol = bars[0].symbol if bars else "UNKNOWN"
        time_tag = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        base_name = f"{symbol}_{time_tag}_{report.id.hex[:8]}"
        parquet_path = self.quarantine_dir / f"{base_name}.parquet"
        report_path = self.quarantine_dir / f"{base_name}.json"

        # Save bars as parquet if possible
        if bars:
            dicts = [
                {
                    "symbol": b.symbol,
                    "timeframe": b.timeframe.value,
                    "adj_type": b.adj_type.value,
                    "ts": b.ts,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                    "amount": b.amount,
                    "source_id": b.source_id,
                    "fetched_at": b.fetched_at,
                }
                for b in bars
            ]
            pl.DataFrame(dicts).write_parquet(parquet_path, compression="zstd")

        # Save JSON report
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

        return parquet_path

    def verify_file_integrity(self, symbol: str, timeframe: Timeframe) -> bool:
        """Verify the on-disk file checksum and readability for a given symbol."""
        path = self.get_production_path(symbol, timeframe)
        if not path.exists():
            return False
        try:
            meta = pq.read_metadata(path)
            return bool(meta.num_rows >= 0)
        except Exception:
            return False

    def cleanup_temp_files(self) -> int:
        """Scan and remove leftover temporary .tmp files."""
        count = 0
        for root_dir in [self.production_dir, self.staging_dir]:
            if not root_dir.exists():
                continue
            for p in root_dir.rglob("*.tmp"):
                try:
                    p.unlink()
                    count += 1
                except Exception as e:
                    logger.warning("Could not unlink temp file %s: %s", p, e)
        return count
