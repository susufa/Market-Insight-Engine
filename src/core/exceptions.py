"""
core/exceptions.py
~~~~~~~~~~~~~~~~~~
Unified business exception hierarchy for Market Insight Engine.

Catching Strategy
-----------------
- Catch `MIEError` to handle any application-level error generically.
- Catch specific subclasses when you need targeted recovery logic.
- Never swallow exceptions silently; always log before re-raising or
  converting to an HTTP error response.
"""

from __future__ import annotations


class MIEError(Exception):
    """Root exception for all Market Insight Engine errors."""

    def __init__(self, message: str, code: str = "MIE_ERROR") -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ── Data Source & Ingestion ─────────────────────────────────────────────── #


class DataSourceError(MIEError):
    """Base for all external data source failures."""


class DataSourceUnavailableError(DataSourceError):
    """Data source is unreachable (network timeout, 5xx, etc.)."""

    def __init__(self, source_id: str, detail: str = "") -> None:
        super().__init__(
            message=f"Data source '{source_id}' is unavailable. {detail}".strip(),
            code="DATA_SOURCE_UNAVAILABLE",
        )
        self.source_id = source_id


class DataSourceRateLimitError(DataSourceError):
    """Request was rejected due to rate limiting (429 / soft-block)."""

    def __init__(self, source_id: str, retry_after: float | None = None) -> None:
        msg = f"Rate limited by '{source_id}'."
        if retry_after:
            msg += f" Retry after {retry_after:.1f}s."
        super().__init__(message=msg, code="DATA_SOURCE_RATE_LIMITED")
        self.source_id = source_id
        self.retry_after = retry_after


class DataSourceSchemaChangedError(DataSourceError):
    """External API returned unexpected fields or structure (breaking change)."""

    def __init__(self, source_id: str, detail: str = "") -> None:
        super().__init__(
            message=f"Schema change detected in '{source_id}'. {detail}".strip(),
            code="DATA_SOURCE_SCHEMA_CHANGED",
        )


# ── Data Quality ────────────────────────────────────────────────────────── #


class DataQualityError(MIEError):
    """Data failed quality gate and was rejected."""

    def __init__(self, symbol: str, reason: str) -> None:
        super().__init__(
            message=f"Quality check failed for '{symbol}': {reason}",
            code="DATA_QUALITY_REJECTED",
        )
        self.symbol = symbol


class DataLeakageDetectedError(MIEError):
    """
    Future information leakage detected in time-series feature computation.
    Raised by anti-leakage guards in the model / analysis layer.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            message=f"Point-in-time violation (data leakage): {detail}",
            code="DATA_LEAKAGE_DETECTED",
        )


# ── Storage ─────────────────────────────────────────────────────────────── #


class StorageError(MIEError):
    """Base for local storage failures."""


class AtomicWriteError(StorageError):
    """Atomic rename / commit to production zone failed."""

    def __init__(self, path: str, detail: str = "") -> None:
        super().__init__(
            message=f"Atomic write failed for '{path}'. {detail}".strip(),
            code="STORAGE_ATOMIC_WRITE_FAILED",
        )


class StorageCorruptionError(StorageError):
    """Stored file failed integrity check (checksum mismatch, truncation)."""

    def __init__(self, path: str) -> None:
        super().__init__(
            message=f"Integrity check failed: '{path}' may be corrupted.",
            code="STORAGE_CORRUPTION",
        )


class DiskSpaceLowError(StorageError):
    """Available disk space has fallen below the safety threshold."""

    def __init__(self, available_gb: float, threshold_gb: float) -> None:
        super().__init__(
            message=(
                f"Disk space low: {available_gb:.2f} GB available, "
                f"threshold is {threshold_gb:.2f} GB."
            ),
            code="STORAGE_DISK_SPACE_LOW",
        )


# ── Hardware / Resource ─────────────────────────────────────────────────── #


class ResourceError(MIEError):
    """Base for local hardware / compute resource failures."""


class GPUUnavailableError(ResourceError):
    """GPU requested but not available; caller should fall back to CPU."""

    def __init__(self, reason: str = "No CUDA-capable GPU detected.") -> None:
        super().__init__(message=reason, code="GPU_UNAVAILABLE")


class GPUOutOfMemoryError(ResourceError):
    """GPU ran out of VRAM during model execution."""

    def __init__(self, model_name: str = "") -> None:
        msg = "GPU out of memory"
        if model_name:
            msg += f" while running '{model_name}'"
        super().__init__(message=msg + ". Fallback to CPU.", code="GPU_OOM")


# ── API / Validation ────────────────────────────────────────────────────── #


class InvalidRequestError(MIEError):
    """API received invalid or logically inconsistent parameters."""

    def __init__(self, detail: str) -> None:
        super().__init__(message=detail, code="INVALID_REQUEST")


class NotFoundError(MIEError):
    """Requested resource (security, bar data, model) does not exist."""

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            message=f"{resource} '{identifier}' not found.",
            code="NOT_FOUND",
        )
