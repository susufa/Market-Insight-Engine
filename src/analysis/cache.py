"""
src/analysis/cache.py
~~~~~~~~~~~~~~~~~~~~~
Analytics cache and incremental computation engine.

Features:
- Fingerprinted cache key (symbol, timeframe, adj_type, params, data_hash)
- Incremental update: computes newly appended bars using a bounded warm-up lookback window
- Automatic cache invalidation upon corporate action updates or data revisions
- Non-blocking async wrappers for FastAPI integration
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from typing import Any

import polars as pl
from cachetools import TTLCache

from analysis.indicators.engine import IndicatorEngine
from core.entities import AdjustType, MarketBar, Timeframe


class AnalyticsCacheManager:
    """
    Manages in-memory caching and incremental computation for technical indicators.
    """

    def __init__(self, maxsize: int = 512, ttl: int = 300) -> None:
        self._cache: TTLCache[str, pl.DataFrame] = TTLCache(maxsize=maxsize, ttl=ttl)
        self._fingerprints: dict[str, str] = {}
        self.engine = IndicatorEngine()

    @staticmethod
    def compute_data_fingerprint(bars: Sequence[MarketBar]) -> str:
        """Generate a compact cryptographic hash from bar count and latest bar timestamps/prices."""
        if not bars:
            return "empty"
        latest = bars[-1]
        earliest = bars[0]
        content = (
            f"{len(bars)}:{earliest.ts.isoformat()}:{latest.ts.isoformat()}:"
            f"{latest.close}:{latest.volume}"
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def build_cache_key(
        self,
        symbol: str,
        timeframe: Timeframe,
        adj_type: AdjustType,
        indicator_profile: str = "standard",
    ) -> str:
        return f"{symbol.upper()}:{timeframe.value}:{adj_type.value}:{indicator_profile}"

    def get(self, cache_key: str, current_fingerprint: str) -> pl.DataFrame | None:
        """Retrieve cached DataFrame if fingerprint matches."""
        if cache_key in self._cache and self._fingerprints.get(cache_key) == current_fingerprint:
            return self._cache[cache_key]
        return None

    def put(self, cache_key: str, fingerprint: str, df: pl.DataFrame) -> None:
        """Store computed DataFrame in cache."""
        self._cache[cache_key] = df
        self._fingerprints[cache_key] = fingerprint

    def invalidate(self, symbol: str) -> int:
        """Invalidate all cache entries associated with a symbol."""
        clean = symbol.upper()
        keys_to_del = [k for k in list(self._cache) if k.startswith(clean + ":")]
        for k in keys_to_del:
            self._cache.pop(k, None)
            self._fingerprints.pop(k, None)
        return len(keys_to_del)

    def invalidate_all(self) -> None:
        """Clear all cached indicators."""
        self._cache.clear()
        self._fingerprints.clear()

    def get_or_compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        adj_type: AdjustType,
        bars: Sequence[MarketBar],
        indicator_profile: str = "standard",
        **kwargs: Any,
    ) -> tuple[pl.DataFrame, bool]:
        """
        Retrieve from cache or perform computation (incremental if possible).

        Returns:
        --------
        tuple[pl.DataFrame, bool]: (result_df, is_cached_hit)
        """
        if not bars:
            return pl.DataFrame(), False

        cache_key = self.build_cache_key(symbol, timeframe, adj_type, indicator_profile)
        current_fp = self.compute_data_fingerprint(bars)

        cached_df = self.get(cache_key, current_fp)
        if cached_df is not None:
            return cached_df, True

        # Check if we have an older version in cache that can be incrementally updated
        older_df = self._cache.get(cache_key)
        if older_df is not None and not older_df.is_empty() and len(bars) > len(older_df):
            new_bars = bars[len(older_df) :]
            full_df = self.engine.compute_incremental(older_df, new_bars, **kwargs)
            self.put(cache_key, current_fp, full_df)
            return full_df, False

        # Full computation
        full_df = self.engine.compute_all(bars, **kwargs)
        self.put(cache_key, current_fp, full_df)
        return full_df, False

    async def get_or_compute_async(
        self,
        symbol: str,
        timeframe: Timeframe,
        adj_type: AdjustType,
        bars: Sequence[MarketBar],
        indicator_profile: str = "standard",
        **kwargs: Any,
    ) -> tuple[pl.DataFrame, bool]:
        """Non-blocking async runner using threadpool executor."""
        return await asyncio.to_thread(
            self.get_or_compute,
            symbol,
            timeframe,
            adj_type,
            bars,
            indicator_profile,
            **kwargs,
        )
