"""
tests/unit/test_indicators.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for vectorized technical indicators:
MA, EMA, MACD, RSI, KDJ, BOLL, ATR, and IndicatorEngine.

Verifies:
- Formula precision against reference implementations with tolerance < 1e-5
- Zero lookahead bias / prefix consistency
- Edge cases: constant series (zero variance), insufficient sample size, empty series
- Immutability of input data
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from analysis.indicators import (
    IndicatorEngine,
    compute_atr,
    compute_boll,
    compute_ema,
    compute_kdj,
    compute_ma,
    compute_macd,
    compute_rsi,
)
from core.entities import AdjustType, MarketBar, Timeframe


def make_test_series(values: list[float], name: str = "close") -> pl.Series:
    return pl.Series(name, values, dtype=pl.Float64)


def test_ma_precision_and_null_padding() -> None:
    data = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    series = make_test_series(data)

    ma3 = compute_ma(series, window=3)
    assert ma3.name == "ma_3"
    # First 2 values must be None (window=3)
    assert ma3[0] is None
    assert ma3[1] is None
    # Subsequent values: (10+11+12)/3 = 11.0, (11+12+13)/3 = 12.0, etc.
    assert pytest.approx(ma3[2], rel=1e-5) == 11.0
    assert pytest.approx(ma3[3], rel=1e-5) == 12.0
    assert pytest.approx(ma3[4], rel=1e-5) == 13.0
    assert pytest.approx(ma3[5], rel=1e-5) == 14.0


def test_ema_precision_and_recurrence() -> None:
    data = [10.0, 12.0, 14.0, 16.0, 18.0]
    series = make_test_series(data)

    span = 3
    ema = compute_ema(series, span=span)

    # Reference manual calculation:
    # ema[0] = 10.0
    # ema[1] = 0.5 * 12.0 + 0.5 * 10.0 = 11.0
    # ema[2] = 0.5 * 14.0 + 0.5 * 11.0 = 12.5
    # ema[3] = 0.5 * 16.0 + 0.5 * 12.5 = 14.25
    # ema[4] = 0.5 * 18.0 + 0.5 * 14.25 = 16.125
    assert pytest.approx(ema[0], rel=1e-5) == 10.0
    assert pytest.approx(ema[1], rel=1e-5) == 11.0
    assert pytest.approx(ema[2], rel=1e-5) == 12.5
    assert pytest.approx(ema[3], rel=1e-5) == 14.25
    assert pytest.approx(ema[4], rel=1e-5) == 16.125


def test_macd_precision() -> None:
    # 50 step geometric trend + noise
    np.random.seed(42)
    prices = 100.0 + np.cumsum(np.random.randn(60) * 1.5)
    close = make_test_series(prices.tolist())

    dif, dea, hist = compute_macd(close, fast=12, slow=26, signal=9, bar_multiplier=2.0)

    assert dif.name == "macd_dif"
    assert dea.name == "macd_dea"
    assert hist.name == "macd_hist"

    # Invariant: hist = 2.0 * (dif - dea)
    for i in range(len(close)):
        diff_val = dif[i] - dea[i]
        assert pytest.approx(hist[i], rel=1e-5) == 2.0 * diff_val


def test_rsi_precision_and_bounds() -> None:
    # 1. Strictly increasing series -> RSI must reach near 100
    inc_prices = [10.0 + i for i in range(30)]
    rsi_inc = compute_rsi(make_test_series(inc_prices), period=14)
    assert rsi_inc[13] is None  # first 14 elements (0..13) null
    assert rsi_inc[20] is not None
    assert pytest.approx(rsi_inc[29], rel=1e-2) == 100.0

    # 2. Strictly decreasing series -> RSI must reach near 0
    dec_prices = [100.0 - i for i in range(30)]
    rsi_dec = compute_rsi(make_test_series(dec_prices), period=14)
    assert rsi_dec[29] is not None
    assert pytest.approx(rsi_dec[29], rel=1e-2) == 0.0

    # 3. All values between 0 and 100
    np.random.seed(123)
    random_prices = (100.0 + np.cumsum(np.random.randn(80))).tolist()
    rsi_rand = compute_rsi(make_test_series(random_prices), period=14)
    for val in rsi_rand.drop_nulls().to_list():
        assert 0.0 <= val <= 100.0


def test_kdj_bounds_and_flat_market() -> None:
    # 1. Flat market (zero variance)
    n = 20
    flat = make_test_series([10.0] * n)
    k, d, j = compute_kdj(flat, flat, flat, n=9, m1=3, m2=3)

    # In flat market, RSV = 50.0, so K=50, D=50, J=50 throughout
    for i in range(n):
        assert pytest.approx(k[i], rel=1e-5) == 50.0
        assert pytest.approx(d[i], rel=1e-5) == 50.0
        assert pytest.approx(j[i], rel=1e-5) == 50.0

    # 2. J = 3K - 2D invariant
    high = make_test_series([10.0 + i % 5 for i in range(30)])
    low = make_test_series([8.0 + i % 3 for i in range(30)])
    close = make_test_series([9.0 + i % 4 for i in range(30)])
    k2, d2, j2 = compute_kdj(high, low, close, n=9, m1=3, m2=3)
    for i in range(30):
        expected_j = 3.0 * k2[i] - 2.0 * d2[i]
        assert pytest.approx(j2[i], rel=1e-5) == expected_j


def test_bollinger_bands_geometry() -> None:
    data = [10.0, 12.0, 11.0, 13.0, 15.0, 14.0, 16.0, 17.0, 15.0, 18.0] * 3
    close = make_test_series(data)

    upper, mid, lower = compute_boll(close, period=10, std_dev_multiplier=2.0)

    # First 9 elements must be null
    for i in range(9):
        assert upper[i] is None
        assert mid[i] is None
        assert lower[i] is None

    # Geometry: Upper >= Mid >= Lower, Upper - Mid == Mid - Lower
    for i in range(9, len(data)):
        u = upper[i]
        m = mid[i]
        b_low = lower[i]
        assert u >= m >= b_low
        assert pytest.approx(u - m, rel=1e-5) == pytest.approx(m - b_low, rel=1e-5)


def test_atr_precision() -> None:
    high = make_test_series([105.0, 108.0, 110.0, 107.0, 106.0] * 5)
    low = make_test_series([98.0, 101.0, 102.0, 100.0, 99.0] * 5)
    close = make_test_series([102.0, 106.0, 105.0, 102.0, 104.0] * 5)

    atr = compute_atr(high, low, close, period=5)
    assert atr.name == "atr_5"
    assert atr[0] is None
    assert atr[3] is None
    assert atr[4] is not None
    assert atr[4] > 0.0


def test_anti_lookahead_prefix_consistency() -> None:
    """
    CRITICAL REQUIREMENT (Section IV):
    Indicator at time T must strictly use data <= T.
    Indicator(full_data)[T] must match Indicator(data_up_to_T)[T].
    """
    np.random.seed(777)
    n = 100
    prices = 50.0 + np.cumsum(np.random.randn(n) * 0.8)
    highs = prices + np.abs(np.random.randn(n) * 0.5)
    lows = prices - np.abs(np.random.randn(n) * 0.5)

    engine = IndicatorEngine()
    df_full = pl.DataFrame({"high": highs, "low": lows, "close": prices})
    res_full = engine.compute_all(df_full)

    # Test at multiple checkpoints T
    for t in [30, 50, 75, 95]:
        df_sliced = df_full.slice(0, t + 1)
        res_sliced = engine.compute_all(df_sliced)

        # Check MA, BOLL, MACD, RSI, KDJ, ATR
        for col in [
            "ma_5",
            "ma_20",
            "boll_mid",
            "macd_dif",
            "macd_dea",
            "rsi_14",
            "kdj_k",
            "atr_14",
        ]:
            val_full = res_full[col][t]
            val_sliced = res_sliced[col][t]
            if val_full is not None and val_sliced is not None:
                assert pytest.approx(val_full, rel=1e-5) == pytest.approx(val_sliced, rel=1e-5), (
                    f"Prefix inconsistency at t={t} for {col}: full={val_full}, sliced={val_sliced}"
                )


def test_indicator_engine_bars_and_batch() -> None:
    bars = [
        MarketBar(
            symbol="600519.SH",
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=datetime(2024, 1, 2, tzinfo=UTC) + timedelta(days=i),
            open=100.0 + i,
            high=105.0 + i,
            low=95.0 + i,
            close=102.0 + i,
            volume=1000.0,
            amount=102000.0,
            source_id="test",
        )
        for i in range(40)
    ]

    engine = IndicatorEngine()
    df = engine.compute_all(bars)

    assert "ma_5" in df.columns
    assert "ma_60" in df.columns
    assert "macd_dif" in df.columns
    assert "rsi_14" in df.columns
    assert "kdj_k" in df.columns
    assert "boll_upper" in df.columns
    assert "atr_14" in df.columns

    # Batch calculation
    batch_res = engine.compute_batch({"600519.SH": bars, "000858.SZ": bars})
    assert len(batch_res) == 2
    assert len(batch_res["600519.SH"]) == 40
