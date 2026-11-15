"""
tests/unit/test_akshare_adapter.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for AKShareAdapter with 100% offline mock coverage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pandas as pd
import pytest

from adapters.akshare_adapter import AKShareAdapter, normalize_symbol_parts
from core.entities import AdjustType, Market, Timeframe
from core.exceptions import (
    DataSourceRateLimitError,
    DataSourceSchemaChangedError,
    DataSourceUnavailableError,
)


def test_normalize_symbol_parts() -> None:
    assert normalize_symbol_parts("600519.SH") == ("600519", "SH")
    assert normalize_symbol_parts("000001.sz") == ("000001", "SZ")
    assert normalize_symbol_parts("00700.HK") == ("00700", "HK")
    assert normalize_symbol_parts("600000") == ("600000", "SH")
    assert normalize_symbol_parts("000002") == ("000002", "SZ")
    assert normalize_symbol_parts("300750") == ("300750", "SZ")
    assert normalize_symbol_parts("832000") == ("832000", "BJ")
    assert normalize_symbol_parts("00700") == ("00700", "HK")


def test_adapter_metadata() -> None:
    adapter = AKShareAdapter()
    assert adapter.source_id == "akshare"
    assert Market.CN_A in adapter.supported_markets
    assert Market.CN_HK in adapter.supported_markets
    assert Market.INDEX in adapter.supported_markets
    assert Timeframe.D1 in adapter.supported_timeframes


@pytest.mark.asyncio
async def test_check_health_success() -> None:
    adapter = AKShareAdapter()
    mock_df = pd.DataFrame({"trade_date": ["2024-01-02"]})
    with patch("akshare.tool_trade_date_hist_sina", return_value=mock_df):
        is_healthy = await adapter.check_health()
        assert is_healthy is True


@pytest.mark.asyncio
async def test_check_health_failure() -> None:
    adapter = AKShareAdapter(max_retries=1)
    with patch("akshare.tool_trade_date_hist_sina", side_effect=ConnectionError("Network down")):
        is_healthy = await adapter.check_health()
        assert is_healthy is False


@pytest.mark.asyncio
async def test_fetch_security_list_cn_a() -> None:
    adapter = AKShareAdapter()
    mock_df = pd.DataFrame(
        {
            "代码": ["600519", "000001"],
            "名称": ["贵州茅台", "平安银行"],
        }
    )
    with patch("akshare.stock_zh_a_spot_em", return_value=mock_df):
        securities = await adapter.fetch_security_list(Market.CN_A)
        assert len(securities) == 2
        assert securities[0].symbol == "600519.SH"
        assert securities[0].name == "贵州茅台"
        assert securities[0].market == Market.CN_A
        assert securities[1].symbol == "000001.SZ"


@pytest.mark.asyncio
async def test_fetch_security_list_hk() -> None:
    adapter = AKShareAdapter()
    mock_df = pd.DataFrame(
        {
            "代码": ["00700"],
            "名称": ["腾讯控股"],
        }
    )
    with patch("akshare.stock_hk_spot_em", return_value=mock_df):
        securities = await adapter.fetch_security_list(Market.CN_HK)
        assert len(securities) == 1
        assert securities[0].symbol == "00700.HK"
        assert securities[0].currency == "HKD"


@pytest.mark.asyncio
async def test_fetch_security_list_schema_error() -> None:
    adapter = AKShareAdapter()
    # Missing '名称' column
    mock_df = pd.DataFrame({"代码": ["600519"]})
    with (
        patch("akshare.stock_zh_a_spot_em", return_value=mock_df),
        pytest.raises(DataSourceSchemaChangedError),
    ):
        await adapter.fetch_security_list(Market.CN_A)


@pytest.mark.asyncio
async def test_fetch_bars_cn_a_normal_and_zero_volume() -> None:
    adapter = AKShareAdapter()
    mock_df = pd.DataFrame(
        {
            "日期": ["2024-01-02", "2024-01-03"],
            "开盘": [100.0, 105.0],
            "最高": [108.0, 105.0],
            "最低": [99.0, 105.0],
            "收盘": [105.0, 105.0],
            "成交量": [1000.0, 0.0],  # Second bar has 0 volume (halted)
            "成交额": [105000.0, 0.0],
        }
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 5, tzinfo=UTC)

    with patch("akshare.stock_zh_a_hist", return_value=mock_df):
        bars = await adapter.fetch_bars("600519.SH", Timeframe.D1, start, end)
        assert len(bars) == 2
        # Normal bar
        b1 = bars[0]
        assert b1.symbol == "600519.SH"
        assert b1.open == 100.0
        assert b1.high == 108.0
        assert b1.low == 99.0
        assert b1.close == 105.0
        assert b1.volume == 1000.0
        assert b1.adj_type == AdjustType.NONE

        # Zero-volume bar: must satisfy open == high == low == close, amount == 0
        b2 = bars[1]
        assert b2.volume == 0.0
        assert b2.amount == 0.0
        assert b2.open == b2.high == b2.low == b2.close == 105.0


@pytest.mark.asyncio
async def test_fetch_bars_schema_error() -> None:
    adapter = AKShareAdapter()
    # Missing required '收盘'
    mock_df = pd.DataFrame(
        {
            "日期": ["2024-01-02"],
            "开盘": [100.0],
            "最高": [108.0],
            "最低": [99.0],
            "成交量": [1000.0],
            "成交额": [105000.0],
        }
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 5, tzinfo=UTC)

    with (
        patch("akshare.stock_zh_a_hist", return_value=mock_df),
        pytest.raises(DataSourceSchemaChangedError),
    ):
        await adapter.fetch_bars("600519.SH", Timeframe.D1, start, end)


@pytest.mark.asyncio
async def test_fetch_adjustment_events() -> None:
    adapter = AKShareAdapter()
    mock_df = pd.DataFrame(
        {
            "除权除息日": ["2024-06-15", "2024-12-01"],
            "现金分红-现金分红比例": ["10.5元", "5.0元"],
            "送转股份-送转总比例": ["2.0股", "0.0股"],
        }
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 12, 31, tzinfo=UTC)

    with patch("akshare.stock_fhps_detail_em", return_value=mock_df):
        events = await adapter.fetch_adjustment_events("600519.SH", start, end)
        assert len(events) == 2
        # Cash dividend is per-share (10.5 / 10 = 1.05)
        assert events[0].cash_dividend == pytest.approx(1.05)
        # Bonus ratio is per-share (2.0 / 10 = 0.2)
        assert events[0].bonus_ratio == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_rate_limit_and_unavailable_exceptions() -> None:
    # 429 Rate limit
    adapter1 = AKShareAdapter(max_retries=1)
    with (
        patch("akshare.stock_zh_a_spot_em", side_effect=Exception("HTTP 429 Too Many Requests")),
        pytest.raises(DataSourceRateLimitError),
    ):
        await adapter1.fetch_security_list(Market.CN_A)

    # Network unavailable
    adapter2 = AKShareAdapter(max_retries=1)
    with (
        patch("akshare.stock_zh_a_spot_em", side_effect=ConnectionError("Failed to connect")),
        pytest.raises(DataSourceUnavailableError),
    ):
        await adapter2.fetch_security_list(Market.CN_A)
