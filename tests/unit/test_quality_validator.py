"""
tests/unit/test_quality_validator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for QualityValidator.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.entities import (
    AdjustType,
    DataQualityStatus,
    MarketBar,
    Timeframe,
)
from quality.validator import QualityValidator


def make_bar(
    symbol: str = "600519.SH",
    ts: datetime | None = None,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: float = 1000.0,
    amount: float = 102000.0,
    timeframe: Timeframe = Timeframe.D1,
) -> MarketBar:
    if ts is None:
        ts = datetime(2024, 1, 2, tzinfo=UTC)
    return MarketBar(
        symbol=symbol,
        timeframe=timeframe,
        adj_type=AdjustType.NONE,
        ts=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        amount=amount,
        source_id="test",
    )


def test_validate_empty_batch() -> None:
    validator = QualityValidator()
    report = validator.validate([], Timeframe.D1)
    assert report.status == DataQualityStatus.PASS
    assert report.total_rows == 0
    assert len(report.violations) == 0


def test_validate_clean_batch_passes() -> None:
    validator = QualityValidator()
    bars = [
        make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC), close=100.0),
        make_bar(ts=datetime(2024, 1, 3, tzinfo=UTC), close=102.0),
        make_bar(ts=datetime(2024, 1, 4, tzinfo=UTC), close=104.0),
    ]
    report = validator.validate(bars, Timeframe.D1)
    assert report.status == DataQualityStatus.PASS
    assert report.total_rows == 3
    assert len(report.violations) == 0


def test_validate_heterogeneous_batch_rejects() -> None:
    validator = QualityValidator()
    bars = [
        make_bar(symbol="600519.SH", ts=datetime(2024, 1, 2, tzinfo=UTC)),
        make_bar(symbol="000001.SZ", ts=datetime(2024, 1, 3, tzinfo=UTC)),
    ]
    report = validator.validate(bars, Timeframe.D1)
    assert report.status == DataQualityStatus.REJECT
    assert any(v.rule == "RULE_HOMOGENEITY" for v in report.violations)


def test_validate_unsorted_chronology_rejects() -> None:
    validator = QualityValidator()
    bars = [
        make_bar(ts=datetime(2024, 1, 4, tzinfo=UTC)),
        make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC)),  # Inversion
    ]
    report = validator.validate(bars, Timeframe.D1)
    assert report.status == DataQualityStatus.REJECT
    assert any(v.rule == "RULE_CHRONOLOGY" for v in report.violations)


def test_validate_duplicate_date_rejects() -> None:
    validator = QualityValidator()
    bars = [
        make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC)),
        make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC)),  # Duplicate
    ]
    report = validator.validate(bars, Timeframe.D1)
    assert report.status == DataQualityStatus.REJECT
    assert any(v.rule == "RULE_DUPLICATES" for v in report.violations)


def test_validate_future_date_rejects() -> None:
    validator = QualityValidator()
    future_ts = datetime.now(UTC) + timedelta(days=100)
    bars = [
        make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC)),
        make_bar(ts=future_ts),
    ]
    report = validator.validate(bars, Timeframe.D1)
    assert report.status == DataQualityStatus.REJECT
    assert any(v.rule == "RULE_FUTURE_DATE" for v in report.violations)


def test_validate_weekend_date_warns() -> None:
    validator = QualityValidator()
    # 2024-01-06 is Saturday
    saturday_ts = datetime(2024, 1, 6, tzinfo=UTC)
    bars = [make_bar(ts=saturday_ts)]
    report = validator.validate(bars, Timeframe.D1)
    assert report.status == DataQualityStatus.WARNING
    assert any(v.rule == "RULE_WEEKEND" for v in report.violations)


def test_validate_price_jump_warns_without_rejection() -> None:
    """Real market jumps (e.g. +40%) must trigger WARNING, not REJECT."""
    validator = QualityValidator()
    bars = [
        make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC), close=100.0),
        make_bar(
            ts=datetime(2024, 1, 3, tzinfo=UTC),
            open_=140.0,
            high=145.0,
            low=138.0,
            close=142.0,  # +42% jump
        ),
    ]
    report = validator.validate(bars, Timeframe.D1)
    assert report.status == DataQualityStatus.WARNING
    assert any(v.rule == "RULE_PRICE_JUMP" for v in report.violations)


def test_validate_data_gap_warns() -> None:
    validator = QualityValidator()
    bars = [
        make_bar(ts=datetime(2024, 1, 2, tzinfo=UTC)),
        make_bar(ts=datetime(2024, 1, 20, tzinfo=UTC)),  # 18-day gap
    ]
    report = validator.validate(bars, Timeframe.D1)
    assert report.status == DataQualityStatus.WARNING
    assert any(v.rule == "RULE_DATA_GAP" for v in report.violations)


def test_validate_conflict_with_existing_bars_warns() -> None:
    validator = QualityValidator()
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    existing = [make_bar(ts=ts, close=100.0)]
    incoming = [
        make_bar(
            ts=ts,
            open_=118.0,
            high=125.0,
            low=115.0,
            close=120.0,
        )
    ]  # 20% difference on same date
    report = validator.validate(incoming, Timeframe.D1, existing_bars=existing)
    assert report.status == DataQualityStatus.WARNING
    assert any(v.rule == "RULE_CONFLICT" for v in report.violations)
