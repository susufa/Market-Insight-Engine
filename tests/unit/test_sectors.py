"""
tests/unit/test_sectors.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for Industry & Concept Sector Analysis.
"""

from __future__ import annotations

import pytest

from analysis.sectors import SectorConstituentQuote, analyze_sectors


def test_sector_analysis_grouping_and_ranking() -> None:
    quotes = [
        # Sector 1: 白酒 (Strong)
        SectorConstituentQuote(
            symbol="600519.SH",
            name="贵州茅台",
            sector_name="食品饮料",
            close=105.0,
            prev_close=100.0,
            volume=1000,
            amount=105000,
        ),
        SectorConstituentQuote(
            symbol="000858.SZ",
            name="五粮液",
            sector_name="食品饮料",
            close=103.0,
            prev_close=100.0,
            volume=800,
            amount=82400,
        ),
        # Sector 2: 电子 (Mixed)
        SectorConstituentQuote(
            symbol="002475.SZ",
            name="立讯精密",
            sector_name="电子",
            close=98.0,
            prev_close=100.0,
            volume=500,
            amount=49000,
        ),
        SectorConstituentQuote(
            symbol="603501.SH",
            name="韦尔股份",
            sector_name="电子",
            close=101.0,
            prev_close=100.0,
            volume=600,
            amount=60600,
        ),
        # Sector 3: 房地产 (Weak)
        SectorConstituentQuote(
            symbol="000002.SZ",
            name="万科A",
            sector_name="房地产",
            close=95.0,
            prev_close=100.0,
            volume=1200,
            amount=114000,
        ),
        # Suspended stock in 房地产
        SectorConstituentQuote(
            symbol="600048.SH",
            name="保利发展",
            sector_name="房地产",
            close=100.0,
            prev_close=100.0,
            volume=0,
            amount=0,
            is_suspended=True,
        ),
    ]

    # Benchmark return = 1.0%
    sectors = analyze_sectors(quotes, benchmark_return_pct=1.0)

    assert len(sectors) == 3

    # Ranking: 食品饮料 (avg +4%) > 电子 (avg -0.5%) > 房地产 (avg -5%)
    assert sectors[0].sector_name == "食品饮料"
    assert pytest.approx(sectors[0].avg_change_pct, rel=1e-3) == 4.0
    assert pytest.approx(sectors[0].relative_strength_vs_bench, rel=1e-3) == 3.0  # 4.0 - 1.0
    assert sectors[0].advance_count == 2
    assert sectors[0].decline_count == 0
    assert "贵州茅台" in sectors[0].top_performer

    assert sectors[1].sector_name == "电子"
    assert pytest.approx(sectors[1].avg_change_pct, rel=1e-3) == -0.5

    assert sectors[2].sector_name == "房地产"
    assert pytest.approx(sectors[2].avg_change_pct, rel=1e-3) == -5.0
    assert sectors[2].constituent_count == 2
    assert sectors[2].active_count == 1
    assert sectors[2].suspended_count == 1


def test_sector_analysis_empty() -> None:
    res = analyze_sectors([])
    assert res == []
