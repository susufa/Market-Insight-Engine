"""
tests/unit/test_volume_normalization.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verification of BarNormalizer:
- Directive 2: Single responsibility normalization
- Directive 4: Single volume conversion & raw value validation
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from src.acquisition.base import RawProviderResponse, VolumeUnit
from src.acquisition.normalizer import BarNormalizer
from src.core.entities import AdjustType, DataOrigin, Timeframe
from src.core.exceptions import DataQualityError, DataSourceSchemaChangedError


@pytest.fixture
def sample_timestamps():
    base = datetime(2023, 1, 3, tzinfo=UTC)
    return [base + timedelta(days=i) for i in range(5)]


def test_volume_normalization_lot_to_share(sample_timestamps):
    """Verify that LOT (手) is deterministically converted to SHARE (* 100)."""
    raw_df = pd.DataFrame(
        [
            {
                "ts": ts.strftime("%Y-%m-%d"),
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 102.0,
                "volume": 500.0,  # 500 lots = 50,000 shares
                "amount": 500.0 * 100.0 * 101.5,  # ~5.15M RMB
            }
            for ts in sample_timestamps
        ]
    )

    raw_resp = RawProviderResponse(
        symbol="600519.SH",
        timeframe=Timeframe.D1,
        raw_df=raw_df,
        raw_payload_text="{}",
        source_id="test_provider",
        source_interface="test:eastmoney_em",
        volume_unit=VolumeUnit.LOT,
        request_ts=datetime.now(UTC),
        response_ts=datetime.now(UTC),
        latency_ms=10.0,
        success=True,
    )

    bars, spec = BarNormalizer.normalize_and_validate(
        raw_resp,
        expected_symbol="600519.SH",
        start=sample_timestamps[0],
        end=sample_timestamps[-1],
    )

    assert len(bars) == 5
    assert spec.unit_conversion_factor == 100.0
    assert spec.raw_volume_unit == VolumeUnit.LOT
    assert spec.normalized_volume_unit == VolumeUnit.SHARE
    assert spec.raw_volume == 2500.0
    assert spec.normalized_volume == 250000.0

    # Verify per-bar volume is converted exactly once
    for bar in bars:
        assert bar.volume == 50000.0  # 500 * 100
        assert bar.adj_type == AdjustType.NONE
        assert bar.data_origin == DataOrigin.REAL_PROVIDER
        assert len(bar.checksum) == 16


def test_volume_normalization_share_to_share(sample_timestamps):
    """Verify that SHARE (股) conversion factor is 1.0 (no double multiplication)."""
    raw_df = pd.DataFrame(
        [
            {
                "ts": ts.strftime("%Y-%m-%d"),
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 102.0,
                "volume": 50000.0,  # Already in shares
                "amount": 50000.0 * 101.5,
            }
            for ts in sample_timestamps
        ]
    )

    raw_resp = RawProviderResponse(
        symbol="600519.SH",
        timeframe=Timeframe.D1,
        raw_df=raw_df,
        raw_payload_text="{}",
        source_id="test_provider",
        source_interface="test:sina_daily",
        volume_unit=VolumeUnit.SHARE,
        request_ts=datetime.now(UTC),
        response_ts=datetime.now(UTC),
        latency_ms=10.0,
        success=True,
    )

    bars, spec = BarNormalizer.normalize_and_validate(
        raw_resp,
        expected_symbol="600519.SH",
        start=sample_timestamps[0],
        end=sample_timestamps[-1],
    )

    assert len(bars) == 5
    assert spec.unit_conversion_factor == 1.0
    assert spec.raw_volume_unit == VolumeUnit.SHARE
    assert spec.normalized_volume == 250000.0

    for bar in bars:
        assert bar.volume == 50000.0  # Kept exactly as 50,000


def test_zero_volume_halted_session():
    """Verify that suspended trading session (vol=0) zeroes amount and flattens OHLC."""
    ts = datetime(2023, 1, 5, tzinfo=UTC)
    raw_df = pd.DataFrame(
        [
            {
                "ts": ts.strftime("%Y-%m-%d"),
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 101.0,
                "volume": 0.0,
                "amount": 5000.0,  # Erroneous amount during suspension
            }
        ]
    )

    raw_resp = RawProviderResponse(
        symbol="600519.SH",
        timeframe=Timeframe.D1,
        raw_df=raw_df,
        raw_payload_text="{}",
        source_id="test_provider",
        source_interface="test:halted",
        volume_unit=VolumeUnit.SHARE,
        request_ts=datetime.now(UTC),
        response_ts=datetime.now(UTC),
        latency_ms=5.0,
        success=True,
    )

    bars, _ = BarNormalizer.normalize_and_validate(
        raw_resp,
        expected_symbol="600519.SH",
        start=ts,
        end=ts,
    )

    assert len(bars) == 1
    bar = bars[0]
    assert bar.volume == 0.0
    assert bar.amount == 0.0
    assert bar.open == bar.high == bar.low == bar.close == 101.0


def test_negative_price_detection_raises_error():
    """Verify that corrupt negative price triggers DataQualityError."""
    ts = datetime(2023, 1, 5, tzinfo=UTC)
    raw_df = pd.DataFrame(
        [
            {
                "ts": ts.strftime("%Y-%m-%d"),
                "open": -10.0,  # Negative corrupt price
                "high": 105.0,
                "low": 98.0,
                "close": 101.0,
                "volume": 1000.0,
                "amount": 100000.0,
            }
        ]
    )

    raw_resp = RawProviderResponse(
        symbol="600519.SH",
        timeframe=Timeframe.D1,
        raw_df=raw_df,
        raw_payload_text="{}",
        source_id="test_provider",
        source_interface="test:corrupt",
        volume_unit=VolumeUnit.SHARE,
        request_ts=datetime.now(UTC),
        response_ts=datetime.now(UTC),
        latency_ms=5.0,
        success=True,
    )

    with pytest.raises(DataQualityError):
        BarNormalizer.normalize_and_validate(
            raw_resp,
            expected_symbol="600519.SH",
            start=ts,
            end=ts,
        )


def test_missing_column_schema_error():
    """Verify missing required OHLCV column raises DataSourceSchemaChangedError."""
    ts = datetime(2023, 1, 5, tzinfo=UTC)
    raw_df = pd.DataFrame(
        [
            {
                "ts": ts.strftime("%Y-%m-%d"),
                "open": 100.0,
                # 'close' missing!
                "high": 105.0,
                "low": 98.0,
                "volume": 1000.0,
                "amount": 100000.0,
            }
        ]
    )

    raw_resp = RawProviderResponse(
        symbol="600519.SH",
        timeframe=Timeframe.D1,
        raw_df=raw_df,
        raw_payload_text="{}",
        source_id="test_provider",
        source_interface="test:missing_close",
        volume_unit=VolumeUnit.SHARE,
        request_ts=datetime.now(UTC),
        response_ts=datetime.now(UTC),
        latency_ms=5.0,
        success=True,
    )

    with pytest.raises(DataSourceSchemaChangedError):
        BarNormalizer.normalize_and_validate(
            raw_resp,
            expected_symbol="600519.SH",
            start=ts,
            end=ts,
        )
