"""
api/v1/market.py
~~~~~~~~~~~~~~~~
High-performance market data endpoints for Market Insight Engine.

Endpoints:
- GET /api/v1/market/securities : Search and filter listed securities
- GET /api/v1/market/bars       : Multi-timeframe OHLCV bars with dynamic QFQ/HFQ adjustments
- GET /api/v1/market/quote      : Latest price quote and summary metrics for a symbol
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from analysis.adjustment import compute_adjusted_bars
from analysis.resample import aggregate_bars
from core.entities import (
    AdjustType,
    DataOrigin,
    Market,
    MarketBar,
    Security,
    Timeframe,
)
from storage.composite_engine import CompositeStorageEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["Market Data"])

# Central storage engine instance (initialized lazily or via lifespan)
_storage_engine: CompositeStorageEngine | None = None

# In-memory hot query LRU cache (512 items, 180s TTL)
_bars_cache: TTLCache[tuple[str, str, str, str, str, int], dict[str, Any]] = TTLCache(
    maxsize=512, ttl=180
)


def invalidate_bars_cache(symbol: str | None = None) -> int:
    """Invalidate bars cache for a symbol, or all symbols if None."""
    global _bars_cache
    if symbol is None:
        count = len(_bars_cache)
        _bars_cache.clear()
        return count
    clean = symbol.upper().strip()
    keys_to_del = [k for k in list(_bars_cache.keys()) if k[0] == clean]
    for k in keys_to_del:
        _bars_cache.pop(k, None)
    return len(keys_to_del)


def _on_storage_write(symbol: str, timeframe: Timeframe) -> None:
    """Callback triggered by storage engine to invalidate cached API bars."""
    invalidate_bars_cache(symbol)


async def get_storage() -> CompositeStorageEngine:
    """Obtain or initialize the singleton CompositeStorageEngine."""
    global _storage_engine
    if _storage_engine is None:
        _storage_engine = CompositeStorageEngine()
        await _storage_engine.initialise()
        _storage_engine.register_post_write_callback(_on_storage_write)
    return _storage_engine


# =========================================================================== #
# Response Schemas
# =========================================================================== #


class BarItem(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


class BarsResponse(BaseModel):
    symbol: str
    timeframe: str
    adj_type: str
    count: int
    data_quality_status: str
    source_id: str
    updated_at: datetime
    is_cached: bool
    bars: list[BarItem]
    data_origin: str = "unknown"
    source_interface: str = ""
    data_fingerprint: str = ""


class SecuritiesResponse(BaseModel):
    total: int
    items: list[Security]


class QuoteResponse(BaseModel):
    symbol: str
    last_price: float
    open: float
    high: float
    low: float
    prev_close: float
    change: float
    pct_change: float
    volume: float
    amount: float
    ts: datetime
    timeframe: str
    data_origin: str = "real_provider"
    source_interface: str = "local_store"


# =========================================================================== #
# Endpoints
# =========================================================================== #


@router.get("/securities", response_model=SecuritiesResponse)
async def list_securities(
    market: Market | None = Query(
        default=None, description="Filter by market (CN_A, CN_HK, INDEX)"
    ),
    search: str | None = Query(default=None, description="Search keyword in symbol or name"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SecuritiesResponse:
    """Retrieve filtered listed securities with pagination."""
    storage = await get_storage()

    sql = (
        "SELECT symbol, name, market, asset_type, listing_status, "
        "listed_date, delisted_date, currency FROM securities WHERE 1=1"
    )
    params: list[Any] = []

    if market:
        sql += " AND market = ?"
        params.append(market.value)

    if search:
        sql += " AND (symbol LIKE ? OR name LIKE ?)"
        term = f"%{search.strip()}%"
        params.extend([term, term])

    # Count total
    count_sql = f"SELECT count(*) as cnt FROM ({sql})"
    async with storage.sqlite.conn.execute(count_sql, params) as cur:
        count_row = await cur.fetchone()
        total = count_row[0] if count_row else 0

    # Paginate
    sql += " ORDER BY symbol ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    items: list[Security] = []
    async with storage.sqlite.conn.execute(sql, params) as cur:
        rows = await cur.fetchall()
        for r in rows:
            items.append(
                Security(
                    symbol=r[0],
                    name=r[1],
                    market=Market(r[2]),
                    asset_type=r[3],
                    listing_status=r[4],
                    listed_date=datetime.fromisoformat(r[5]) if r[5] else None,
                    delisted_date=datetime.fromisoformat(r[6]) if r[6] else None,
                    currency=r[7],
                )
            )

    return SecuritiesResponse(total=total, items=items)


@router.get("/bars", response_model=BarsResponse)
async def get_bars(
    symbol: str = Query(..., description="Canonical symbol, e.g. '600519.SH'"),
    timeframe: Timeframe = Query(
        default=Timeframe.D1, description="Bar frequency: 1d, 1w, 1M, 1Q, 1Y"
    ),
    adj_type: AdjustType = Query(default=AdjustType.NONE, description="Adjustment: none, qfq, hfq"),
    start: datetime | None = Query(default=None, description="Start date (UTC)"),
    end: datetime | None = Query(default=None, description="End date (UTC)"),
    limit: int = Query(default=1000, ge=1, le=5000),
) -> BarsResponse:
    """
    Fetch multi-timeframe OHLCV bars with dynamic adjustment calculation
    and memory caching.
    """
    clean_symbol = symbol.upper().strip()
    storage = await get_storage()

    # Cache key
    cache_key = (
        clean_symbol,
        timeframe.value,
        adj_type.value,
        start.isoformat() if start else "",
        end.isoformat() if end else "",
        limit,
    )
    if cache_key in _bars_cache:
        cached_data = _bars_cache[cache_key]
        cached_resp = BarsResponse(**cached_data)
        return cached_resp.model_copy(update={"is_cached": True})

    # Default date range if not specified: last 10 years to now
    range_start = start or datetime(2010, 1, 1, tzinfo=UTC)
    range_end = end or datetime.now(UTC)

    # 1. Read raw daily bars from local storage
    raw_df = await storage.read_bars(
        symbol=clean_symbol,
        timeframe=Timeframe.D1,
        start=range_start,
        end=range_end,
    )

    if raw_df.is_empty():
        # Check if symbol exists in securities
        sec = await storage.get_security(clean_symbol)
        return BarsResponse(
            symbol=clean_symbol,
            timeframe=timeframe.value,
            adj_type=adj_type.value,
            count=0,
            data_quality_status="NOT_FOUND" if sec is None else "NO_DATA",
            source_id="local_store",
            updated_at=datetime.now(UTC),
            is_cached=False,
            bars=[],
            data_origin="unknown",
            source_interface="",
            data_fingerprint="",
        )

    # Convert DataFrame to canonical MarketBar entities
    raw_bars = [
        MarketBar(
            symbol=clean_symbol,
            timeframe=Timeframe.D1,
            adj_type=AdjustType.NONE,
            ts=r["ts"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
            amount=r["amount"],
            source_id=r.get("source_id", "local_store"),
            data_origin=DataOrigin(r.get("data_origin", "real_provider")),
            source_interface=r.get("source_interface", ""),
            checksum=r.get("checksum", ""),
        )
        for r in raw_df.to_dicts()
    ]

    # 2. Dynamic adjustment calculation (QFQ / HFQ / NONE)
    if adj_type != AdjustType.NONE:
        events = await storage.read_adjustment_events(
            symbol=clean_symbol,
            start=datetime(2000, 1, 1, tzinfo=UTC),
            end=range_end,
        )
        adjusted_bars = compute_adjusted_bars(raw_bars, events, adj_type)
    else:
        adjusted_bars = raw_bars

    # 3. Timeframe aggregation / resampling (1d -> 1w, 1M, 1Q, 1Y)
    resampled_bars = aggregate_bars(adjusted_bars, timeframe)

    # Slice to requested limit (most recent bars)
    final_bars = resampled_bars[-limit:] if len(resampled_bars) > limit else resampled_bars

    bar_items = [
        BarItem(
            ts=b.ts,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
            amount=b.amount,
        )
        for b in final_bars
    ]

    first_bar = final_bars[0] if final_bars else None
    last_bar = final_bars[-1] if final_bars else None
    data_origin_val = str(getattr(first_bar, "data_origin", "unknown")) if first_bar else "unknown"
    source_interface_val = str(getattr(first_bar, "source_interface", "")) if first_bar else ""
    data_fp_val = (
        hashlib.sha256(
            f"{clean_symbol}:{len(final_bars)}:{last_bar.checksum}".encode()
        ).hexdigest()[:16]
        if last_bar
        else ""
    )

    result_dict: dict[str, Any] = {
        "symbol": clean_symbol,
        "timeframe": timeframe.value,
        "adj_type": adj_type.value,
        "count": len(bar_items),
        "data_quality_status": "PASS",
        "source_id": first_bar.source_id if first_bar else "local_store",
        "updated_at": datetime.now(UTC),
        "is_cached": False,
        "bars": bar_items,
        "data_origin": data_origin_val,
        "source_interface": source_interface_val,
        "data_fingerprint": data_fp_val,
    }

    # Store in LRU cache
    _bars_cache[cache_key] = result_dict

    return BarsResponse(**result_dict)


@router.get("/quote", response_model=QuoteResponse)
async def get_quote(
    symbol: str = Query(..., description="Canonical symbol, e.g. '600519.SH'"),
) -> QuoteResponse:
    """Retrieve the latest quote and change metrics for a security."""
    clean_symbol = symbol.upper().strip()
    storage = await get_storage()

    raw_df = await storage.read_bars(
        symbol=clean_symbol,
        timeframe=Timeframe.D1,
        start=datetime(2010, 1, 1, tzinfo=UTC),
        end=datetime.now(UTC),
    )

    if raw_df.is_empty():
        raise HTTPException(
            status_code=404, detail=f"No quote data found for symbol '{clean_symbol}'"
        )

    rows = raw_df.tail(2).to_dicts()
    latest = rows[-1]
    last_price = float(latest["close"])
    open_price = float(latest["open"])
    high_price = float(latest["high"])
    low_price = float(latest["low"])
    volume = float(latest["volume"])
    amount = float(latest["amount"])
    ts = latest["ts"]

    prev_close = float(rows[0]["close"]) if len(rows) > 1 else open_price

    change = round(last_price - prev_close, 4)
    pct_change = round((change / prev_close) * 100.0, 2) if prev_close > 0 else 0.0

    return QuoteResponse(
        symbol=clean_symbol,
        last_price=last_price,
        open=open_price,
        high=high_price,
        low=low_price,
        prev_close=prev_close,
        change=change,
        pct_change=pct_change,
        volume=volume,
        amount=amount,
        ts=ts,
        timeframe="1d",
        data_origin=str(latest.get("data_origin", "real_provider")),
        source_interface=str(latest.get("source_interface", "local_store")),
    )
