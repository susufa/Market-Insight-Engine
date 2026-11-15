"""
quality/validator.py
~~~~~~~~~~~~~~~~~~~~
Concrete implementation of BaseQualityValidator.

Evaluates data batches against strict quality gates before allowing
transition from Staging to Production.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.entities import (
    DataQualityReport,
    DataQualityStatus,
    MarketBar,
    QualityViolation,
    Timeframe,
)
from core.interfaces.quality import BaseQualityValidator
from quality.calendar import TradingCalendar


class QualityValidator(BaseQualityValidator):
    """
    Data Quality Manager (DQM) validator.

    Applies the following rule catalog:
    - RULE_HOMOGENEITY: All bars in batch must share symbol and timeframe (REJECT).
    - RULE_OHLC_GEOMETRY: High >= max(O,C), Low <= min(O,C), Low > 0 (REJECT).
    - RULE_VOLUME_CONSISTENCY: Volume >= 0, Amount >= 0, zero-volume asserts (REJECT).
    - RULE_CHRONOLOGY: Bars must be strictly ordered by ts (REJECT).
    - RULE_DUPLICATES: No duplicate timestamps allowed (REJECT).
    - RULE_FUTURE_DATE: No bars with timestamps in the future (REJECT).
    - RULE_WEEKEND: Bars falling on non-trading weekend days (WARNING).
    - RULE_PRICE_JUMP: Abnormal single-day price movement > 35% (WARNING).
    - RULE_DATA_GAP: Extended gap (> 7 calendar days) between trading bars (WARNING).
    - RULE_CONFLICT: Significant divergence from existing historical bars (WARNING).
    """

    def __init__(self, future_tolerance_hours: float = 24.0) -> None:
        self.future_tolerance = timedelta(hours=future_tolerance_hours)

    def validate(
        self,
        bars: list[MarketBar],
        timeframe: Timeframe,
        *,
        existing_bars: list[MarketBar] | None = None,
    ) -> DataQualityReport:
        """Run all quality rules against `bars`."""
        if not bars:
            return DataQualityReport(
                symbol="",
                timeframe=timeframe,
                source_id="",
                total_rows=0,
                status=DataQualityStatus.PASS,
                notes="Empty bar batch provided; nothing to validate.",
            )

        symbol = bars[0].symbol
        source_id = bars[0].source_id
        violations: list[QualityViolation] = []

        # -------------------------------------------------------------- #
        # Rule 1: Batch Homogeneity
        # -------------------------------------------------------------- #
        heterogeneous_symbols = {b.symbol for b in bars if b.symbol != symbol}
        heterogeneous_timeframes = {b.timeframe for b in bars if b.timeframe != timeframe}
        if heterogeneous_symbols or heterogeneous_timeframes:
            violations.append(
                QualityViolation(
                    rule="RULE_HOMOGENEITY",
                    severity=DataQualityStatus.REJECT,
                    description=(
                        f"Batch contains mixed symbols ({heterogeneous_symbols}) "
                        f"or timeframes ({heterogeneous_timeframes})."
                    ),
                    affected_rows=len(heterogeneous_symbols) + len(heterogeneous_timeframes),
                )
            )

        # -------------------------------------------------------------- #
        # Rule 2: Chronological Ordering & Duplicates & Future Dates
        # -------------------------------------------------------------- #
        seen_timestamps: set[datetime] = set()
        duplicate_count = 0
        unsorted_count = 0
        future_count = 0
        weekend_count = 0
        ohlc_geometry_count = 0
        volume_inconsistency_count = 0

        now_utc = datetime.now(UTC)
        max_allowed_ts = now_utc + self.future_tolerance

        prev_bar: MarketBar | None = None

        for bar in bars:
            # OHLC Geometry
            if (
                bar.high < max(bar.open, bar.close)
                or bar.low > min(bar.open, bar.close)
                or bar.open <= 0
                or bar.high <= 0
                or bar.low <= 0
                or bar.close <= 0
            ):
                ohlc_geometry_count += 1

            # Volume Consistency
            if (
                bar.volume < 0
                or bar.amount < 0
                or bar.volume == 0
                and (bar.amount != 0 or not (bar.open == bar.high == bar.low == bar.close))
            ):
                volume_inconsistency_count += 1

            # Future date check
            if bar.ts > max_allowed_ts:
                future_count += 1

            # Duplicates check
            if bar.ts in seen_timestamps:
                duplicate_count += 1
            else:
                seen_timestamps.add(bar.ts)

            # Ordering check
            if prev_bar is not None and bar.ts <= prev_bar.ts:
                unsorted_count += 1

            # Weekend check (for daily bars)
            if timeframe == Timeframe.D1 and TradingCalendar.is_weekend(bar.ts.date()):
                weekend_count += 1

            prev_bar = bar

        if ohlc_geometry_count > 0:
            violations.append(
                QualityViolation(
                    rule="RULE_OHLC_GEOMETRY",
                    severity=DataQualityStatus.REJECT,
                    description=f"{ohlc_geometry_count} bars violate OHLC geometric bounds.",
                    affected_rows=ohlc_geometry_count,
                )
            )

        if volume_inconsistency_count > 0:
            violations.append(
                QualityViolation(
                    rule="RULE_VOLUME_CONSISTENCY",
                    severity=DataQualityStatus.REJECT,
                    description=f"{volume_inconsistency_count} bars have invalid volume or amount.",
                    affected_rows=volume_inconsistency_count,
                )
            )

        if duplicate_count > 0:
            violations.append(
                QualityViolation(
                    rule="RULE_DUPLICATES",
                    severity=DataQualityStatus.REJECT,
                    description=f"Found {duplicate_count} duplicate timestamp records in batch.",
                    affected_rows=duplicate_count,
                )
            )

        if unsorted_count > 0:
            violations.append(
                QualityViolation(
                    rule="RULE_CHRONOLOGY",
                    severity=DataQualityStatus.REJECT,
                    description=(
                        f"Bars are not strictly sorted in chronological order "
                        f"({unsorted_count} inversions)."
                    ),
                    affected_rows=unsorted_count,
                )
            )

        if future_count > 0:
            violations.append(
                QualityViolation(
                    rule="RULE_FUTURE_DATE",
                    severity=DataQualityStatus.REJECT,
                    description=(
                        f"Found {future_count} bars with timestamps in the future beyond tolerance."
                    ),
                    affected_rows=future_count,
                )
            )

        if weekend_count > 0:
            violations.append(
                QualityViolation(
                    rule="RULE_WEEKEND",
                    severity=DataQualityStatus.WARNING,
                    description=(
                        f"Found {weekend_count} bars dated on weekend days (Saturday/Sunday)."
                    ),
                    affected_rows=weekend_count,
                )
            )

        # -------------------------------------------------------------- #
        # Rule 3: Abnormal Price Jump & Trading Day Gaps
        # -------------------------------------------------------------- #
        price_jump_count = 0
        gap_count = 0

        for i in range(1, len(bars)):
            p0 = bars[i - 1].close
            p1 = bars[i].close
            if p0 > 0:
                pct_change = abs(p1 - p0) / p0
                if pct_change > 0.35:
                    price_jump_count += 1

            # Gap check (> 10 calendar days between consecutive bars)
            delta_days = (bars[i].ts.date() - bars[i - 1].ts.date()).days
            if delta_days > 10:
                gap_count += 1

        if price_jump_count > 0:
            violations.append(
                QualityViolation(
                    rule="RULE_PRICE_JUMP",
                    severity=DataQualityStatus.WARNING,
                    description=(
                        f"Detected {price_jump_count} bars with single-day price movement > 35%. "
                        "May be due to corporate actions or extreme market volatility."
                    ),
                    affected_rows=price_jump_count,
                )
            )

        if gap_count > 0:
            violations.append(
                QualityViolation(
                    rule="RULE_DATA_GAP",
                    severity=DataQualityStatus.WARNING,
                    description=(
                        f"Detected {gap_count} trading gaps > 10 calendar days "
                        "(potential trading suspension)."
                    ),
                    affected_rows=gap_count,
                )
            )

        # -------------------------------------------------------------- #
        # Rule 4: Regression / Conflict with Existing Data
        # -------------------------------------------------------------- #
        if existing_bars:
            existing_by_ts = {b.ts: b for b in existing_bars}
            conflict_count = 0
            for bar in bars:
                if bar.ts in existing_by_ts:
                    old_b = existing_by_ts[bar.ts]
                    if old_b.close > 0 and abs(bar.close - old_b.close) / old_b.close > 0.01:
                        conflict_count += 1

            if conflict_count > 0:
                violations.append(
                    QualityViolation(
                        rule="RULE_CONFLICT",
                        severity=DataQualityStatus.WARNING,
                        description=(
                            f"Detected {conflict_count} bars where incoming price differs > 1% "
                            "from existing historical record on the same date."
                        ),
                        affected_rows=conflict_count,
                    )
                )

        return DataQualityReport(
            symbol=symbol,
            timeframe=timeframe,
            source_id=source_id,
            total_rows=len(bars),
            violations=violations,
        )
