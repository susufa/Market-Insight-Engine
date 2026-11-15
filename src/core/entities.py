"""
core/entities.py
~~~~~~~~~~~~~~~~
Canonical domain entities for Market Insight Engine.

These are the ONLY representations allowed to cross module boundaries.
Adapters must convert external data into these types BEFORE passing data
to any storage, analysis, or model layer.

Design rules
------------
- All monetary / price fields are plain Python `float` (no Decimal) for
  vectorised computation efficiency.  Precision is validated on ingestion.
- Timestamps are always timezone-aware UTC internally; display conversion
  to local market timezone is a presentation concern.
- Never add external-library-specific types here (no pandas, polars, torch).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

# =========================================================================== #
# Enumerations
# =========================================================================== #


class Market(StrEnum):
    """Supported markets (expand as needed)."""

    CN_A = "CN_A"  # China A-share (SSE + SZSE)
    CN_HK = "CN_HK"  # Hong Kong (HKEX)
    US = "US"  # United States (NYSE / NASDAQ)
    INDEX = "INDEX"  # Cross-market index bucket


class AssetType(StrEnum):
    STOCK = "stock"
    INDEX = "index"
    ETF = "etf"
    FUND = "fund"
    SECTOR = "sector"  # Industry / concept sector aggregate


class AdjustType(StrEnum):
    """Price adjustment (复权) type."""

    NONE = "none"  # 不复权 – raw historical prices
    QFQ = "qfq"  # 前复权 – forward-adjusted (most recent price as anchor)
    HFQ = "hfq"  # 后复权 – backward-adjusted (IPO price as anchor)


class DataOrigin(StrEnum):
    """Data provenance and authenticity origin."""

    REAL_PROVIDER = "real_provider"  # Directly from authenticated market data provider
    MANUAL_IMPORT = "manual_import"  # Manually imported verified historical data
    SYNTHETIC_TEST = "synthetic_test"  # Explicitly generated synthetic / mock data for tests
    UNKNOWN = "unknown"  # Unverified / indeterminate origin


class Timeframe(StrEnum):
    """Bar / K-line aggregation frequency."""

    D1 = "1d"
    W1 = "1w"
    MN1 = "1M"
    Q1 = "1Q"
    Y1 = "1Y"
    # Minute-level (Phase 2+)
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"


class ListingStatus(StrEnum):
    LISTED = "listed"
    DELISTED = "delisted"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


class DataQualityStatus(StrEnum):
    PASS = "PASS"  # Passed all quality checks → Production zone
    WARNING = "WARNING"  # Minor issues; usable with caveats
    REJECT = "REJECT"  # Fatal issues → Quarantine zone


# =========================================================================== #
# Core Domain Entities
# =========================================================================== #


class Security(BaseModel):
    """Canonical representation of a listed security / index / sector."""

    model_config = {"frozen": True}

    symbol: str = Field(
        ...,
        description="Normalised symbol, e.g. '600519.SH', '0700.HK', 'AAPL.US'",
        min_length=1,
        max_length=20,
    )
    name: str = Field(..., description="Human-readable display name", min_length=1)
    market: Market
    asset_type: AssetType
    listing_status: ListingStatus = ListingStatus.UNKNOWN
    listed_date: datetime | None = None
    delisted_date: datetime | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()


class MarketBar(BaseModel):
    """
    A single OHLCV bar (K-line) in canonical form.

    Storage invariant: the bottom-layer Parquet store ONLY holds
    adj_type=NONE (raw / unadjusted) bars.  Adjusted series are
    computed dynamically from AdjustmentEvent records at query time.
    """

    model_config = {"frozen": True}

    # Identity
    symbol: str
    timeframe: Timeframe
    adj_type: AdjustType = AdjustType.NONE

    # Time  (UTC, timezone-aware)
    ts: datetime = Field(..., description="Bar open timestamp in UTC")

    # OHLCV
    open: float = Field(..., gt=0, description="Opening price")
    high: float = Field(..., gt=0, description="Highest price")
    low: float = Field(..., gt=0, description="Lowest price")
    close: float = Field(..., gt=0, description="Closing price")
    volume: float = Field(..., ge=0, description="Volume in shares / contracts")
    amount: float = Field(..., ge=0, description="Turnover in currency units")

    # Provenance
    source_id: str = Field(..., description="Adapter identifier, e.g. 'akshare'")
    data_origin: DataOrigin = Field(
        default=DataOrigin.UNKNOWN,
        description="Authenticity origin (real_provider, manual_import, synthetic_test, unknown)",
    )
    source_interface: str = Field(
        default="",
        description="Underlying API or interface name, e.g. 'akshare:stock_zh_a_daily'",
    )
    checksum: str = Field(
        default="",
        description="Payload or record SHA-256 fingerprint for auditability",
    )
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("ts", "fetched_at", mode="before")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware (UTC required).")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def validate_ohlc_geometry(self) -> MarketBar:
        """
        Geometric and volume consistency checks:
        1. High ≥ max(Open, Close) and Low ≤ min(Open, Close).
        2. When volume == 0 (e.g. halted/suspended trading session):
           - Turnover amount must also be 0.
           - Open == High == Low == Close (no price variation possible with zero trades).
        """
        if self.high < max(self.open, self.close):
            raise ValueError(
                f"High ({self.high}) must be ≥ max(open, close) ({max(self.open, self.close)})"
            )
        if self.low > min(self.open, self.close):
            raise ValueError(
                f"Low ({self.low}) must be ≤ min(open, close) ({min(self.open, self.close)})"
            )
        if self.volume == 0:
            if self.amount != 0:
                raise ValueError(
                    f"Turnover amount must be 0 when volume is 0, got amount={self.amount}"
                )
            if not (self.open == self.high == self.low == self.close):
                raise ValueError(
                    f"When volume is 0 (e.g. halted/suspended), Open, High, Low, and Close "
                    f"must be identical, got O={self.open}, H={self.high}, "
                    f"L={self.low}, C={self.close}"
                )
        return self


class AdjustmentEvent(BaseModel):
    """
    A corporate action that affects the price series (ex-dividend / split).
    Used to dynamically compute QFQ / HFQ series without mutating raw bars.
    """

    model_config = {"frozen": True}

    symbol: str
    ex_date: datetime  # Ex-right / ex-dividend date (UTC midnight)
    # Cash dividend per share (in security's currency)
    cash_dividend: float = Field(default=0.0, ge=0)
    # Bonus shares ratio (e.g. 0.5 means 5 bonus shares per 10 held)
    bonus_ratio: float = Field(default=0.0, ge=0)
    # Rights issue ratio and price
    rights_ratio: float = Field(default=0.0, ge=0)
    rights_price: float = Field(default=0.0, ge=0)
    source_id: str = ""


# =========================================================================== #
# Data Quality
# =========================================================================== #


class QualityViolation(BaseModel):
    """A single rule violation found during data quality checks."""

    rule: str  # e.g. "OHLC_GEOMETRY", "DUPLICATE_DATE"
    severity: DataQualityStatus
    description: str
    affected_rows: int = 0


class DataQualityReport(BaseModel):
    """Aggregated quality assessment for a batch of bars."""

    id: UUID = Field(default_factory=uuid4)
    symbol: str
    timeframe: Timeframe
    source_id: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_rows: int = 0
    status: DataQualityStatus = DataQualityStatus.PASS
    violations: list[QualityViolation] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _derive_status(self) -> DataQualityReport:
        """Derive overall status from worst violation severity."""
        if any(v.severity == DataQualityStatus.REJECT for v in self.violations):
            self.status = DataQualityStatus.REJECT
        elif (
            any(v.severity == DataQualityStatus.WARNING for v in self.violations)
            and self.status == DataQualityStatus.PASS
        ):
            self.status = DataQualityStatus.WARNING
        return self


# =========================================================================== #
# Data Provenance & Revision Audit Entities (Step6)
# =========================================================================== #


class RawResponseArchive(BaseModel):
    """
    Audit record for raw external data source responses.
    Ensures complete, cryptographic traceability from external API to MarketBar.
    """

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid4()))
    provider_name: str
    source_interface: str
    request_ts: datetime
    request_params: dict[str, str] = Field(default_factory=dict)
    response_status: str = "SUCCESS"  # "SUCCESS", "EMPTY", "ERROR"
    response_ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_response_hash: str
    normalized_data_hash: str
    symbol: str
    market: Market
    row_count: int = 0
    raw_payload_path: str = ""
    transformation_version: str = "v1.0"


class DataRevisionRecord(BaseModel):
    """
    Audit record for historical data revisions / retrospective adjustments.
    """

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    timeframe: Timeframe
    revised_ts_count: int
    sample_diffs: list[dict[str, str]] = Field(default_factory=list)
    old_fingerprint: str
    new_fingerprint: str
    revised_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str = "retrospective_update"
