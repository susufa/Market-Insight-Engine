"""
tests/unit/test_contracts.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Structural contract tests: verify every abstract interface can be
subclassed and instantiated with concrete implementations.

These tests act as a build-time guard – if any abstract method signature
changes without updating implementations, this suite fails immediately.

Run with:
    pytest tests/unit/test_contracts.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from core.entities import (
    AdjustmentEvent,
    DataQualityReport,
    DataQualityStatus,
    Market,
    MarketBar,
    Security,
    Timeframe,
)
from core.interfaces import (
    BaseDataSourceAdapter,
    BasePredictor,
    BaseQualityValidator,
    BaseStorageEngine,
)

# ---------------------------------------------------------------------------
# Minimal concrete stubs – just enough to satisfy ABCs
# ---------------------------------------------------------------------------


class _StubAdapter(BaseDataSourceAdapter):
    @property
    def source_id(self) -> str:
        return "stub"

    @property
    def supported_markets(self) -> list[Market]:
        return [Market.CN_A]

    @property
    def supported_timeframes(self) -> list[Timeframe]:
        return [Timeframe.D1]

    async def check_health(self) -> bool:
        return True

    async def fetch_security_list(self, market: Market) -> list[Security]:
        return []

    async def fetch_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        return []

    async def fetch_adjustment_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[AdjustmentEvent]:
        return []


class _StubStorage(BaseStorageEngine):
    async def initialise(self) -> None: ...
    async def close(self) -> None: ...
    async def upsert_securities(self, securities: list[Security]) -> int:
        return 0

    async def get_security(self, symbol: str) -> Security | None:
        return None

    async def write_bars(self, bars: list[MarketBar], *, overwrite_existing: bool = False) -> int:
        return 0

    async def read_bars(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> pl.DataFrame:
        return pl.DataFrame()

    async def write_adjustment_events(self, events: list[AdjustmentEvent]) -> int:
        return 0

    async def read_adjustment_events(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[AdjustmentEvent]:
        return []

    async def query(self, sql: str, params: dict[str, Any] | None = None) -> pl.DataFrame:
        return pl.DataFrame()

    async def get_coverage(
        self, symbol: str, timeframe: Timeframe
    ) -> tuple[datetime | None, datetime | None]:
        return None, None

    async def verify_integrity(self, symbol: str, timeframe: Timeframe) -> bool:
        return True


class _StubValidator(BaseQualityValidator):
    def validate(
        self,
        bars: list[MarketBar],
        timeframe: Timeframe,
        *,
        existing_bars: list[MarketBar] | None = None,
    ) -> DataQualityReport:
        return DataQualityReport(
            symbol=bars[0].symbol if bars else "UNKNOWN",
            timeframe=timeframe,
            source_id="stub",
            total_rows=len(bars),
            status=DataQualityStatus.PASS,
        )


class _StubPredictor(BasePredictor):
    @property
    def model_name(self) -> str:
        return "stub_model"

    @property
    def model_version(self) -> str:
        return "0.0.1"

    @property
    def task_description(self) -> str:
        return "Stub predictor for contract tests"

    def fit(self, features: pl.DataFrame, labels: pl.Series, *, train_end: datetime) -> None: ...

    def predict(
        self,
        features: pl.DataFrame,
        *,
        as_of: datetime,
        horizon: int,
        timeframe: Timeframe,
    ) -> dict[str, Any]:
        return {
            "point_estimate": 0.0,
            "lower_bound": -0.05,
            "upper_bound": 0.05,
            "confidence": 0.5,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "as_of": as_of,
        }

    def evaluate(
        self,
        features: pl.DataFrame,
        labels: pl.Series,
        *,
        eval_start: datetime,
    ) -> dict[str, float]:
        return {"mae": 0.0}

    def save(self, directory: Path) -> Path:
        return directory

    def load(self, directory: Path) -> None: ...
    def release(self) -> None: ...


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdapterContract:
    def test_stub_adapter_instantiates(self) -> None:
        adapter = _StubAdapter()
        assert adapter.source_id == "stub"
        assert Market.CN_A in adapter.supported_markets
        assert Timeframe.D1 in adapter.supported_timeframes

    def test_is_base_data_source_adapter(self) -> None:
        assert isinstance(_StubAdapter(), BaseDataSourceAdapter)


class TestStorageContract:
    def test_stub_storage_instantiates(self) -> None:
        storage = _StubStorage()
        assert isinstance(storage, BaseStorageEngine)


class TestValidatorContract:
    def test_stub_validator_returns_report(self) -> None:
        validator = _StubValidator()
        assert isinstance(validator, BaseQualityValidator)
        report = validator.validate([], Timeframe.D1)
        assert report.status == DataQualityStatus.PASS


class TestPredictorContract:
    def test_stub_predictor_instantiates(self) -> None:
        predictor = _StubPredictor()
        assert isinstance(predictor, BasePredictor)
        assert predictor.model_name == "stub_model"

    def test_predict_returns_required_keys(self) -> None:
        predictor = _StubPredictor()
        result = predictor.predict(
            pl.DataFrame(),
            as_of=datetime(2024, 1, 2, tzinfo=UTC),
            horizon=5,
            timeframe=Timeframe.D1,
        )
        for key in ("point_estimate", "lower_bound", "upper_bound", "confidence"):
            assert key in result, f"Missing key '{key}' in predict() output"
