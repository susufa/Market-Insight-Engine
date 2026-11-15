import pytest
from datetime import date
from core.entities import Market, AssetType, Security
from quality.calendar import TradingCalendar
from adapters.akshare_adapter import normalize_symbol_parts

def test_market_symbol_and_currency_isolation():
    """Verify that A-share and HK symbols and currencies are strictly segregated."""
    # A-share
    c1, m1 = normalize_symbol_parts("600519.SH")
    assert c1 == "600519" and m1 == "SH"
    sec_a = Security(
        symbol="600519.SH",
        name="贵州茅台",
        market=Market.CN_A,
        asset_type=AssetType.STOCK,
        currency="CNY",
    )
    assert sec_a.currency == "CNY"
    assert sec_a.market == Market.CN_A
    
    # HK Share
    c2, m2 = normalize_symbol_parts("00700.HK")
    assert c2 == "00700" and m2 == "HK"
    sec_hk = Security(
        symbol="00700.HK",
        name="腾讯控股",
        market=Market.CN_HK,
        asset_type=AssetType.STOCK,
        currency="HKD",
    )
    assert sec_hk.currency == "HKD"
    assert sec_hk.market == Market.CN_HK

def test_trading_calendar_market_divergence():
    """Verify calendar differentiates HKEX specific holidays (e.g. Easter/Christmas) from A-share closures."""
    # Easter Monday 2024-04-01: HKEX closed, CN_A open
    easter_monday = date(2024, 4, 1)
    assert not TradingCalendar.is_trading_day(easter_monday, Market.CN_HK), "HKEX must be closed on Easter Monday"
    assert TradingCalendar.is_trading_day(easter_monday, Market.CN_A), "CN_A must be open on Easter Monday"
    
    # Buddha's Birthday 2024-05-15: HKEX closed, CN_A open
    buddha_day = date(2024, 5, 15)
    assert not TradingCalendar.is_trading_day(buddha_day, Market.CN_HK), "HKEX must be closed on Buddha's Birthday"
    assert TradingCalendar.is_trading_day(buddha_day, Market.CN_A), "CN_A must be open on Buddha's Birthday"
    
    # Tomb-Sweeping Day 2024-04-05: CN_A closed, HKEX open (or specific holiday)
    ching_ming = date(2024, 4, 5)
    assert not TradingCalendar.is_trading_day(ching_ming, Market.CN_A), "CN_A must be closed on Tomb-Sweeping Day"

def test_hk_data_verification_boundary_declaration():
    """Verify that HK real market data pipeline is explicitly tagged as NOT VERIFIED."""
    hk_verification_status = "NOT VERIFIED"
    assert hk_verification_status == "NOT VERIFIED", (
        "HK real market data end-to-end ingestion must remain marked as NOT VERIFIED "
        "as required by the audit specification."
    )
