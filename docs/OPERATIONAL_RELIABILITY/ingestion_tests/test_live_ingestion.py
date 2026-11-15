import asyncio
import sys
import os
import json
import time
from datetime import datetime, UTC

sys.path.insert(0, ".")
sys.path.insert(0, "src")

from src.adapters.akshare_adapter import AKShareAdapter, normalize_symbol_parts
from src.core.entities import Timeframe, Market
from src.core.exceptions import DataSourceUnavailableError, DataSourceRateLimitError

async def run_ingestion_audit():
    adapter = AKShareAdapter(requests_per_second=1.0, max_retries=2, request_timeout=10.0)
    
    # 1. Health check
    print("--- 1. Testing Adapter Health Check ---")
    t0 = time.time()
    try:
        health_ok = await adapter.check_health()
        print(f"Health check status: {health_ok} (took {time.time()-t0:.2f}s)")
    except Exception as exc:
        health_ok = False
        print(f"Health check exception: {exc}")

    symbols = ["600519.SH", "000001.SZ", "000333.SZ"]
    start_dt = datetime(2023, 12, 1, tzinfo=UTC)
    end_dt = datetime(2023, 12, 29, tzinfo=UTC)
    
    results = {}
    
    # 2. Repeated fetching test (2 iterations each to verify stability & rate-limiting)
    print("\n--- 2. Repeated Fetching Test on Target Symbols ---")
    for symbol in symbols:
        results[symbol] = []
        for trial in range(1, 3):
            t_req = time.time()
            try:
                bars = await adapter.fetch_bars(symbol, Timeframe.D1, start_dt, end_dt)
                elapsed = time.time() - t_req
                res = {
                    "trial": trial,
                    "symbol": symbol,
                    "status": "SUCCESS",
                    "bars_count": len(bars),
                    "first_bar_date": bars[0].ts.strftime("%Y-%m-%d") if bars else None,
                    "last_bar_date": bars[-1].ts.strftime("%Y-%m-%d") if bars else None,
                    "first_close": bars[0].close if bars else None,
                    "last_close": bars[-1].close if bars else None,
                    "elapsed_sec": round(elapsed, 3),
                    "source_id": adapter.source_id,
                }
                print(f"[{symbol}] Trial {trial}: SUCCESS - {len(bars)} bars, range: {res['first_bar_date']} -> {res['last_bar_date']}, elapsed: {elapsed:.2f}s")
            except Exception as e:
                elapsed = time.time() - t_req
                res = {
                    "trial": trial,
                    "symbol": symbol,
                    "status": "FAILED",
                    "error_type": type(e).__name__,
                    "error_msg": str(e),
                    "elapsed_sec": round(elapsed, 3)
                }
                print(f"[{symbol}] Trial {trial}: FAILED - {type(e).__name__}: {e}")
            results[symbol].append(res)
            await asyncio.sleep(1.0) # Respectful delay
            
    out_file = "docs/OPERATIONAL_RELIABILITY/ingestion_tests/LIVE_INGESTION_RESULTS.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "health_check": health_ok,
            "test_timestamp": datetime.now(UTC).isoformat(),
            "results": results
        }, f, indent=2)
    print(f"\nResults saved to {out_file}")

if __name__ == "__main__":
    asyncio.run(run_ingestion_audit())
