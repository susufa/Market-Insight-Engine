"""
tests/unit/test_acquisition_providers.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for AKShareProvider and MockProvider contracts and behavior.
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pandas as pd
import pytest

from src.acquisition.base import VolumeUnit
from src.acquisition.providers.akshare_provider import AKShareProvider, normalize_symbol_parts
from src.acquisition.providers.mock_provider import MockProvider
from src.core.entities import Timeframe


def test_normalize_symbol_parts():
    """Verify code and exchange extraction across symbols."""
    assert normalize_symbol_parts("600519.SH") == ("600519", "SH")
    assert normalize_symbol_parts("000001.SZ") == ("000001", "SZ")
    assert normalize_symbol_parts("00700.HK") == ("00700", "HK")
    # Inferred
    assert normalize_symbol_parts("600519") == ("600519", "SH")
    assert normalize_symbol_parts("000858") == ("000858", "SZ")
    assert normalize_symbol_parts("00700") == ("00700", "HK")


@pytest.mark.asyncio
async def test_mock_provider_fetch_raw_bars():
    """Verify MockProvider generates synthetic raw responses without normalizing volume."""
    provider = MockProvider(volume_unit=VolumeUnit.SHARE)
    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 15, tzinfo=UTC)

    raw_resp = await provider.fetch_raw_bars("600519.SH", Timeframe.D1, start, end)

    assert raw_resp.success is True
    assert raw_resp.volume_unit == VolumeUnit.SHARE
    assert not raw_resp.raw_df.empty
    assert "volume" in raw_resp.raw_df.columns
    assert raw_resp.source_id == "mock"


@pytest.mark.asyncio
async def test_akshare_provider_raw_fetch_sina_declaration():
    """Verify AKShareProvider sets volume_unit=VolumeUnit.SHARE when querying Sina."""
    provider = AKShareProvider()
    mock_df = pd.DataFrame(
        [
            {
                "date": "2023-01-03",
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.0,
                "volume": 2500000.0,
                "amount": 252500000.0,
            }
        ]
    )

    with (
        patch("akshare.stock_zh_a_daily", return_value=mock_df),
        patch("akshare.stock_zh_a_hist", side_effect=Exception("EM connection timeout")),
    ):
        raw_resp = await provider.fetch_raw_bars(
            "600519.SH",
            Timeframe.D1,
            datetime(2023, 1, 1, tzinfo=UTC),
            datetime(2023, 1, 10, tzinfo=UTC),
        )

        assert raw_resp.success is True
        assert raw_resp.volume_unit == VolumeUnit.SHARE
        assert raw_resp.source_interface == "akshare:stock_zh_a_daily"
        assert len(raw_resp.raw_df) == 1
        # Provider does NOT normalize volume
        assert raw_resp.raw_df.iloc[0]["volume"] == 2500000.0


@pytest.mark.asyncio
async def test_akshare_provider_raw_fetch_eastmoney_declaration():
    """Verify AKShareProvider sets volume_unit=VolumeUnit.LOT when querying EastMoney."""
    provider = AKShareProvider()
    mock_df = pd.DataFrame(
        [
            {
                "日期": "2023-01-03",
                "开盘": 100.0,
                "最高": 102.0,
                "最低": 99.0,
                "收盘": 101.0,
                "成交量": 25000.0,  # 25,000 hands
                "成交额": 252500000.0,
            }
        ]
    )

    with patch("akshare.stock_zh_a_hist", return_value=mock_df):
        raw_resp = await provider.fetch_raw_bars(
            "600519.SH",
            Timeframe.D1,
            datetime(2023, 1, 1, tzinfo=UTC),
            datetime(2023, 1, 10, tzinfo=UTC),
        )

        assert raw_resp.success is True
        assert raw_resp.volume_unit == VolumeUnit.LOT
        assert raw_resp.source_interface == "akshare:stock_zh_a_hist"
        assert len(raw_resp.raw_df) == 1
        # Provider does NOT normalize volume
        assert raw_resp.raw_df.iloc[0]["成交量"] == 25000.0
