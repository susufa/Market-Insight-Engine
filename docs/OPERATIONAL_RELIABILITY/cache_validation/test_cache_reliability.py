import time
from datetime import datetime, UTC, timedelta
import pytest
import polars as pl

from core.entities import MarketBar, Timeframe, AdjustType, DataOrigin
from analysis.cache import AnalyticsCacheManager

def make_sample_bars(symbol: str, count: int, start_date: datetime, tf: Timeframe = Timeframe.D1, adj: AdjustType = AdjustType.NONE):
    bars = []
    for i in range(count):
        dt = start_date + timedelta(days=i)
        bars.append(
            MarketBar(
                symbol=symbol,
                timeframe=tf,
                adj_type=adj,
                ts=dt,
                open=100.0 + i,
                high=105.0 + i,
                low=95.0 + i,
                close=102.0 + i,
                volume=10000.0,
                amount=1020000.0,
                source_id="akshare",
                data_origin=DataOrigin.REAL_PROVIDER,
                source_interface="akshare:stock_zh_a_daily",
                checksum="chk",
                fetched_at=datetime.now(UTC),
            )
        )
    return bars

def test_cache_hit_and_data_refresh():
    """Cache returns hit for identical data, but refreshes immediately when new bars arrive."""
    cache = AnalyticsCacheManager(ttl=60)
    symbol = "600519.SH"
    base_dt = datetime(2023, 1, 1, tzinfo=UTC)
    bars50 = make_sample_bars(symbol, 50, base_dt)
    
    # 1. First call -> Cache Miss
    df1, is_hit1 = cache.get_or_compute(symbol, Timeframe.D1, AdjustType.NONE, bars50)
    assert not is_hit1
    assert len(df1) == 50
    
    # 2. Repeated call with same data -> Cache Hit
    df2, is_hit2 = cache.get_or_compute(symbol, Timeframe.D1, AdjustType.NONE, bars50)
    assert is_hit2
    assert len(df2) == 50
    
    # 3. New bar appended -> Fingerprint changes -> Cache Miss (fresh computation)
    bars51 = make_sample_bars(symbol, 51, base_dt)
    df3, is_hit3 = cache.get_or_compute(symbol, Timeframe.D1, AdjustType.NONE, bars51)
    assert not is_hit3
    assert len(df3) == 51

def test_cache_cross_symbol_and_timeframe_isolation():
    """Cache keys must be strictly segregated across symbol, timeframe, and adj_type."""
    cache = AnalyticsCacheManager(ttl=60)
    base_dt = datetime(2023, 1, 1, tzinfo=UTC)
    
    bars_moutai = make_sample_bars("600519.SH", 40, base_dt)
    bars_pingan = make_sample_bars("000001.SZ", 40, base_dt)
    
    # Compute for Moutai
    df_m, hit_m = cache.get_or_compute("600519.SH", Timeframe.D1, AdjustType.NONE, bars_moutai)
    assert not hit_m
    
    # PingAn must NOT hit Moutai's cache
    df_p, hit_p = cache.get_or_compute("000001.SZ", Timeframe.D1, AdjustType.NONE, bars_pingan)
    assert not hit_p
    
    # Different timeframe must NOT hit D1 cache
    bars_w1 = make_sample_bars("600519.SH", 40, base_dt, tf=Timeframe.W1)
    df_w, hit_w = cache.get_or_compute("600519.SH", Timeframe.W1, AdjustType.NONE, bars_w1)
    assert not hit_w

def test_cache_invalidation():
    """invalidate(symbol) must selectively purge that symbol's cached entries."""
    cache = AnalyticsCacheManager(ttl=60)
    base_dt = datetime(2023, 1, 1, tzinfo=UTC)
    
    bars_m = make_sample_bars("600519.SH", 30, base_dt)
    bars_p = make_sample_bars("000001.SZ", 30, base_dt)
    
    cache.get_or_compute("600519.SH", Timeframe.D1, AdjustType.NONE, bars_m)
    cache.get_or_compute("000001.SZ", Timeframe.D1, AdjustType.NONE, bars_p)
    
    # Invalidate Moutai only
    purged = cache.invalidate("600519.SH")
    assert purged >= 1
    
    # Moutai is now miss
    _, hit_m2 = cache.get_or_compute("600519.SH", Timeframe.D1, AdjustType.NONE, bars_m)
    assert not hit_m2
    
    # PingAn is still hit
    _, hit_p2 = cache.get_or_compute("000001.SZ", Timeframe.D1, AdjustType.NONE, bars_p)
    assert hit_p2

def test_cache_ttl_expiration():
    """Cache entries expire after TTL seconds."""
    cache = AnalyticsCacheManager(ttl=1) # 1-second TTL
    base_dt = datetime(2023, 1, 1, tzinfo=UTC)
    bars = make_sample_bars("600519.SH", 30, base_dt)
    
    _, hit1 = cache.get_or_compute("600519.SH", Timeframe.D1, AdjustType.NONE, bars)
    assert not hit1
    
    _, hit2 = cache.get_or_compute("600519.SH", Timeframe.D1, AdjustType.NONE, bars)
    assert hit2
    
    # Wait for TTL to expire
    time.sleep(1.2)
    _, hit3 = cache.get_or_compute("600519.SH", Timeframe.D1, AdjustType.NONE, bars)
    assert not hit3, "Entry must expire after TTL"
