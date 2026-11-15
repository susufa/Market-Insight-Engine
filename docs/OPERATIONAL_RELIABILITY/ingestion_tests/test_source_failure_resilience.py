import pytest
from datetime import datetime, UTC
from unittest.mock import patch
import pandas as pd

from adapters.akshare_adapter import AKShareAdapter
from core.entities import Timeframe, Market, DataOrigin
from core.exceptions import (
    DataSourceUnavailableError,
    DataSourceRateLimitError,
    DataSourceSchemaChangedError,
)

@pytest.fixture
def adapter():
    return AKShareAdapter(max_retries=1, request_timeout=2.0)

@pytest.mark.asyncio
async def test_upstream_timeout_error(adapter):
    """Verify network timeout raises DataSourceUnavailableError cleanly without crash."""
    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 10, tzinfo=UTC)
    with patch("akshare.stock_zh_a_hist", side_effect=TimeoutError("Request timed out")), \
         patch("akshare.stock_zh_a_daily", side_effect=TimeoutError("Fallback timed out")):
        with pytest.raises(DataSourceUnavailableError) as exc_info:
            await adapter.fetch_bars("600519.SH", Timeframe.D1, start, end)
        assert "akshare" in str(exc_info.value).lower()

@pytest.mark.asyncio
async def test_upstream_rate_limit_error(adapter):
    """Verify rate limit triggers DataSourceRateLimitError with retry_after."""
    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 10, tzinfo=UTC)
    with patch("akshare.stock_zh_a_hist", side_effect=Exception("HTTP 429 Too Many Requests")), \
         patch("akshare.stock_zh_a_daily", side_effect=Exception("429 Too Many Requests")):
        with pytest.raises(DataSourceRateLimitError) as exc_info:
            await adapter.fetch_bars("600519.SH", Timeframe.D1, start, end)
        assert exc_info.value.retry_after > 0

@pytest.mark.asyncio
async def test_empty_response_returns_empty_list(adapter):
    """Verify empty upstream dataframe returns empty list, never fabricated bars."""
    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 10, tzinfo=UTC)
    with patch("akshare.stock_zh_a_hist", return_value=pd.DataFrame()), \
         patch("akshare.stock_zh_a_daily", return_value=pd.DataFrame()):
        bars = await adapter.fetch_bars("600519.SH", Timeframe.D1, start, end)
        assert bars == []

@pytest.mark.asyncio
async def test_schema_changed_missing_column(adapter):
    """Verify missing required column raises DataSourceSchemaChangedError."""
    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 10, tzinfo=UTC)
    bad_df = pd.DataFrame({
        "日期": ["2023-01-03"],
        "开盘": [1800.0],
        "最高": [1850.0],
        "最低": [1790.0],
        "成交量": [10000.0],
        "成交额": [18000000.0]
    })
    with patch("akshare.stock_zh_a_hist", return_value=bad_df):
        with pytest.raises(DataSourceSchemaChangedError) as exc_info:
            await adapter.fetch_bars("600519.SH", Timeframe.D1, start, end)
        assert "Missing expected column" in str(exc_info.value)

@pytest.mark.asyncio
async def test_provenance_and_checksum_integrity(adapter):
    """Verify returned real bars have explicit real_provider origin and sha256 checksum."""
    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 10, tzinfo=UTC)
    good_df = pd.DataFrame({
        "日期": ["2023-01-03"],
        "开盘": [1800.0],
        "最高": [1850.0],
        "最低": [1790.0],
        "收盘": [1830.0],
        "成交量": [10000.0],
        "成交额": [18000000.0]
    })
    with patch("akshare.stock_zh_a_hist", return_value=good_df):
        bars = await adapter.fetch_bars("600519.SH", Timeframe.D1, start, end)
        assert len(bars) == 1
        bar = bars[0]
        assert bar.data_origin == DataOrigin.REAL_PROVIDER
        assert bar.source_interface == "akshare:stock_zh_a_hist"
        assert len(bar.checksum) > 8
