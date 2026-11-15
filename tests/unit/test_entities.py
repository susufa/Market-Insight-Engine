"""
tests/unit/test_entities.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Contract tests for core domain entities.

These tests verify that:
1. Valid data is accepted without error.
2. Invalid data (bad OHLC geometry, missing fields, naive datetimes) is
   rejected at construction time by Pydantic validators.
3. Enum values are correctly constrained.

Run with:
    pytest tests/unit/test_entities.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from core.entities import (
    AdjustType,
    AssetType,
    DataQualityReport,
    DataQualityStatus,
    ListingStatus,
    Market,
    MarketBar,
    QualityViolation,
    Security,
    Timeframe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _valid_bar(**overrides: object) -> MarketBar:
    defaults = {
        "symbol": "600519.SH",
        "timeframe": Timeframe.D1,
        "adj_type": AdjustType.NONE,
        "ts": _utc(2024, 1, 2),
        "open": 1800.0,
        "high": 1850.0,
        "low": 1780.0,
        "close": 1820.0,
        "volume": 10_000.0,
        "amount": 18_200_000.0,
        "source_id": "akshare",
    }
    defaults.update(overrides)
    return MarketBar(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Security entity
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_valid_security(self) -> None:
        s = Security(
            symbol="600519.sh",  # lowercase → should be normalised
            name="贵州茅台",
            market=Market.CN_A,
            asset_type=AssetType.STOCK,
            listing_status=ListingStatus.LISTED,
            currency="CNY",
        )
        assert s.symbol == "600519.SH"  # validator uppercases

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            Security(
                symbol="000001.SZ", market=Market.CN_A, asset_type=AssetType.STOCK
            )  # missing name

    def test_invalid_market_raises(self) -> None:
        with pytest.raises(ValidationError):
            Security(symbol="X", name="X", market="INVALID_MKT", asset_type=AssetType.STOCK)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MarketBar entity – positive cases
# ---------------------------------------------------------------------------


class TestMarketBarValid:
    def test_valid_bar_constructs(self) -> None:
        bar = _valid_bar()
        assert bar.symbol == "600519.SH"
        assert bar.adj_type == AdjustType.NONE

    def test_high_equals_open_or_close(self) -> None:
        """High may equal max(open, close); should be accepted."""
        bar = _valid_bar(open=1850.0, high=1850.0, low=1780.0, close=1820.0)
        assert bar.high == bar.open

    def test_low_equals_open_or_close(self) -> None:
        bar = _valid_bar(open=1820.0, high=1850.0, low=1780.0, close=1780.0)
        assert bar.low == bar.close

    def test_all_same_ohlc(self) -> None:
        """Doji candle: open = high = low = close."""
        bar = _valid_bar(open=1800.0, high=1800.0, low=1800.0, close=1800.0)
        assert bar.open == bar.close


# ---------------------------------------------------------------------------
# MarketBar entity – negative cases (OHLC geometry violations)
# ---------------------------------------------------------------------------


class TestMarketBarOHLCGeometry:
    def test_high_below_open_raises(self) -> None:
        with pytest.raises(ValidationError, match="High"):
            _valid_bar(open=1900.0, high=1850.0, low=1780.0, close=1820.0)

    def test_high_below_close_raises(self) -> None:
        with pytest.raises(ValidationError, match="High"):
            _valid_bar(open=1800.0, high=1810.0, low=1780.0, close=1850.0)

    def test_low_above_open_raises(self) -> None:
        with pytest.raises(ValidationError, match="Low"):
            _valid_bar(open=1800.0, high=1850.0, low=1810.0, close=1800.0)

    def test_negative_price_raises(self) -> None:
        with pytest.raises(ValidationError):
            _valid_bar(open=-1.0, high=1850.0, low=1780.0, close=1820.0)

    def test_negative_volume_raises(self) -> None:
        with pytest.raises(ValidationError):
            _valid_bar(volume=-100.0)


# ---------------------------------------------------------------------------
# MarketBar entity – zero volume (halted/suspended) consistency rules
# ---------------------------------------------------------------------------


class TestMarketBarZeroVolume:
    def test_valid_zero_volume_bar(self) -> None:
        """When volume=0 and amount=0 with flat OHLC (halted stock), bar is valid."""
        bar = _valid_bar(
            open=1800.0,
            high=1800.0,
            low=1800.0,
            close=1800.0,
            volume=0.0,
            amount=0.0,
        )
        assert bar.volume == 0.0
        assert bar.amount == 0.0
        assert bar.open == bar.high == bar.low == bar.close

    def test_zero_volume_positive_amount_raises(self) -> None:
        """Zero volume cannot have positive turnover amount."""
        with pytest.raises(ValidationError, match="Turnover amount must be 0 when volume is 0"):
            _valid_bar(
                open=1800.0,
                high=1800.0,
                low=1800.0,
                close=1800.0,
                volume=0.0,
                amount=5000.0,
            )

    def test_zero_volume_price_variation_raises(self) -> None:
        """Zero volume cannot have varying high/low prices."""
        with pytest.raises(ValidationError, match="must be identical"):
            _valid_bar(
                open=1800.0,
                high=1850.0,
                low=1800.0,
                close=1800.0,
                volume=0.0,
                amount=0.0,
            )


# ---------------------------------------------------------------------------
# MarketBar entity – timezone enforcement
# ---------------------------------------------------------------------------


class TestMarketBarTimezone:
    def test_naive_datetime_raises(self) -> None:
        """Naive datetimes (no tzinfo) must be rejected."""
        with pytest.raises(ValidationError):
            _valid_bar(ts=datetime(2024, 1, 2))  # naive – no tzinfo

    def test_non_utc_converted_to_utc(self) -> None:
        """Non-UTC aware datetimes should be converted, not rejected."""
        from datetime import timedelta

        cst = timezone(timedelta(hours=8))
        ts_cst = datetime(2024, 1, 2, 9, 30, tzinfo=cst)
        bar = _valid_bar(ts=ts_cst)
        assert bar.ts.tzinfo == UTC


# ---------------------------------------------------------------------------
# DataQualityReport
# ---------------------------------------------------------------------------


class TestDataQualityReport:
    def test_no_violations_gives_pass(self) -> None:
        report = DataQualityReport(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            source_id="akshare",
            total_rows=250,
        )
        assert report.status == DataQualityStatus.PASS
        assert report.violations == []

    def test_reject_violation_escalates_status(self) -> None:
        report = DataQualityReport(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            source_id="akshare",
            total_rows=10,
            violations=[
                QualityViolation(
                    rule="OHLC_GEOMETRY",
                    severity=DataQualityStatus.REJECT,
                    description="High < Close",
                    affected_rows=2,
                )
            ],
        )
        assert report.status == DataQualityStatus.REJECT

    def test_warning_violation_escalates_to_warning(self) -> None:
        report = DataQualityReport(
            symbol="000001.SZ",
            timeframe=Timeframe.D1,
            source_id="akshare",
            total_rows=5,
            violations=[
                QualityViolation(
                    rule="SINGLE_SOURCE",
                    severity=DataQualityStatus.WARNING,
                    description="Only one data source available",
                    affected_rows=5,
                )
            ],
        )
        assert report.status == DataQualityStatus.WARNING
