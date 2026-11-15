"""core package – canonical domain model and interface contracts."""

from core.entities import (
    AdjustmentEvent,
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
from core.exceptions import (
    AtomicWriteError,
    DataLeakageDetectedError,
    DataQualityError,
    DataSourceError,
    DataSourceRateLimitError,
    DataSourceSchemaChangedError,
    DataSourceUnavailableError,
    DiskSpaceLowError,
    GPUOutOfMemoryError,
    GPUUnavailableError,
    InvalidRequestError,
    MIEError,
    NotFoundError,
    StorageCorruptionError,
    StorageError,
)

__all__ = [
    # Entities
    "Security",
    "MarketBar",
    "AdjustmentEvent",
    "DataQualityReport",
    "QualityViolation",
    # Enums
    "Market",
    "AssetType",
    "AdjustType",
    "Timeframe",
    "ListingStatus",
    "DataQualityStatus",
    # Exceptions
    "MIEError",
    "DataSourceError",
    "DataSourceUnavailableError",
    "DataSourceRateLimitError",
    "DataSourceSchemaChangedError",
    "DataQualityError",
    "DataLeakageDetectedError",
    "StorageError",
    "AtomicWriteError",
    "StorageCorruptionError",
    "DiskSpaceLowError",
    "GPUUnavailableError",
    "GPUOutOfMemoryError",
    "InvalidRequestError",
    "NotFoundError",
]
