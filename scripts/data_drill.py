"""
scripts/data_drill.py
~~~~~~~~~~~~~~~~~~~~~
Phase 2 Data Ingestion Drill Script:
Runs initial historical ingestion drill on 100 benchmark A-share stocks
across a 6-year period (2018-01-01 to 2023-12-31).

Records real results without fabrication:
- Coverage rate
- Success count & failure count
- Per-stock latency and row count
- Quality validation status
- Preserves outputs in reports/gate2_drill_report.json
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any

# Ensure project root and src are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from adapters.akshare_adapter import AKShareAdapter
from config import get_settings
from core.entities import DataQualityStatus, Timeframe
from quality.validator import QualityValidator
from storage.composite_engine import CompositeStorageEngine

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DataDrill")

BENCHMARK_100: list[str] = [
    "600519.SH", "000858.SZ", "601318.SH", "300750.SZ", "000001.SZ",
    "000333.SZ", "600036.SH", "601166.SH", "002594.SZ", "600900.SH",
    "601888.SH", "600276.SH", "601012.SH", "002475.SZ", "300059.SZ",
    "600030.SH", "000002.SZ", "601398.SH", "601288.SH", "601988.SH",
    "601939.SH", "600000.SH", "600016.SH", "601658.SH", "601998.SH",
    "600887.SH", "000568.SZ", "002304.SZ", "600809.SH", "603288.SH",
    "000725.SZ", "002415.SZ", "300122.SZ", "300760.SZ", "688981.SH",
    "600104.SH", "601668.SH", "601628.SH", "601601.SH", "601766.SH",
    "601857.SH", "600028.SH", "601088.SH", "601899.SH", "600585.SH",
    "600309.SH", "002460.SZ", "002466.SZ", "600438.SH", "601800.SH",
    "601186.SH", "601390.SH", "601989.SH", "601727.SH", "600150.SH",
    "601985.SH", "600011.SH", "600905.SH", "600025.SH", "600886.SH",
    "000963.SZ", "002236.SZ", "300015.SZ", "300450.SZ", "688111.SH",
    "688012.SH", "688036.SH", "002049.SZ", "002241.SZ", "002027.SZ",
    "002714.SZ", "000876.SZ", "000651.SZ", "000063.SZ", "002456.SZ",
    "002352.SZ", "600690.SH", "600745.SH", "600584.SH", "600703.SH",
    "600111.SH", "600436.SH", "600048.SH", "600346.SH", "600383.SH",
    "600115.SH", "601111.SH", "600009.SH", "601006.SH", "601818.SH",
    "601919.SH", "601872.SH", "600019.SH", "000709.SZ", "000938.SZ",
    "002142.SZ", "002271.SZ", "002812.SZ", "300014.SZ", "300274.SZ",
]


async def run_data_drill() -> dict[str, Any]:
    settings = get_settings()
    settings.ensure_data_dirs()

    adapter = AKShareAdapter(requests_per_second=4.0, max_retries=3, request_timeout=20.0)
    validator = QualityValidator()
    storage = CompositeStorageEngine()
    await storage.initialise()

    start_date = datetime(2018, 1, 1, tzinfo=UTC)
    end_date = datetime(2023, 12, 31, tzinfo=UTC)

    logger.info("Starting Gate 2 Ingestion Drill: %d symbols over 6 years", len(BENCHMARK_100))
    overall_start_time = time.time()

    drill_results: list[dict[str, Any]] = []
    success_count = 0
    warning_count = 0
    reject_count = 0
    fail_count = 0
    total_bars_ingested = 0

    ip_throttled = False
    throttle_reason = ""

    for idx, symbol in enumerate(BENCHMARK_100, 1):
        item_start = time.time()
        res: dict[str, Any] = {
            "symbol": symbol,
            "status": "UNKNOWN",
            "bars": 0,
            "start": None,
            "end": None,
            "latency_ms": 0.0,
            "error": None,
        }

        if ip_throttled:
            res["status"] = "UPSTREAM_RATE_LIMITED"
            res["error"] = f"Upstream IP throttle active: {throttle_reason}. Query halted to obey access policy."
            fail_count += 1
            drill_results.append(res)
            logger.warning("[%d/%d] %s: Skipped (Upstream IP Throttled)", idx, len(BENCHMARK_100), symbol)
            continue

        try:
            # 1. Fetch bars from AKShare
            bars = await adapter.fetch_bars(
                symbol=symbol,
                timeframe=Timeframe.D1,
                start=start_date,
                end=end_date,
            )

            if not bars:
                res["status"] = "EMPTY"
                res["error"] = "No bars returned by data source"
                fail_count += 1
            else:
                # 2. Quality validation
                report = validator.validate(bars, Timeframe.D1)
                res["status"] = report.status.value
                res["bars"] = len(bars)
                res["start"] = bars[0].ts.strftime("%Y-%m-%d")
                res["end"] = bars[-1].ts.strftime("%Y-%m-%d")

                if report.status in (DataQualityStatus.PASS, DataQualityStatus.WARNING):
                    # 3. Atomic commit to production storage
                    written = await storage.write_bars(bars, overwrite_existing=True)
                    total_bars_ingested += written
                    if report.status == DataQualityStatus.PASS:
                        success_count += 1
                    else:
                        warning_count += 1
                else:
                    # Route to quarantine
                    storage.parquet.route_to_quarantine(bars, report)
                    reject_count += 1
                    res["error"] = [v.model_dump(mode="json") for v in report.violations]

        except Exception as e:
            err_str = str(e)
            res["status"] = "ERROR"
            res["error"] = err_str
            fail_count += 1
            logger.error("[%d/%d] %s FAILED: %s", idx, len(BENCHMARK_100), symbol, err_str)

            # Check if Eastmoney has throttled this IP
            if "临时限流" in err_str or "断开了连接" in err_str or "429" in err_str:
                ip_throttled = True
                throttle_reason = "EastMoney push2 server IP throttle detected"
                logger.warning("Upstream IP throttle detected; pausing further network requests to respect provider.")

        item_latency = (time.time() - item_start) * 1000.0
        res["latency_ms"] = round(item_latency, 2)
        drill_results.append(res)

        logger.info(
            "[%d/%d] %s: %s | bars=%d | latency=%.1fms",
            idx,
            len(BENCHMARK_100),
            symbol,
            res["status"],
            res["bars"],
            item_latency,
        )

    total_duration = time.time() - overall_start_time
    coverage_rate = (success_count + warning_count) / len(BENCHMARK_100) * 100.0

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_symbols_attempted": len(BENCHMARK_100),
        "target_range": {"start": "2018-01-01", "end": "2023-12-31", "years": 6},
        "successful_ingestions": success_count,
        "warning_ingestions": warning_count,
        "rejected_ingestions": reject_count,
        "failed_or_empty": fail_count,
        "coverage_rate_percent": round(coverage_rate, 2),
        "total_bars_ingested": total_bars_ingested,
        "total_duration_seconds": round(total_duration, 2),
        "average_symbol_latency_ms": round((total_duration / len(BENCHMARK_100)) * 1000.0, 2),
        "details": drill_results,
    }

    # Save to reports/gate2_drill_report.json
    report_dir = Path("reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "gate2_drill_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("Drill complete. Report saved to %s", report_file)
    logger.info(
        "Summary: Coverage=%.1f%%, Total Bars=%d, Time=%.1fs",
        coverage_rate,
        total_bars_ingested,
        total_duration,
    )

    await storage.close()
    return summary


if __name__ == "__main__":
    asyncio.run(run_data_drill())
