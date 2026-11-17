# Market Insight Engine (MIE)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Polars-1.12%2B-CD792C?logo=polars&logoColor=white" alt="Polars">
  <img src="https://img.shields.io/badge/DuckDB-OLAP-FFF000?logo=duckdb&logoColor=black" alt="DuckDB">
  <img src="https://img.shields.io/badge/SQLite-WAL%20ACID-003B57?logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React 19">
  <img src="https://img.shields.io/badge/TypeScript-5.6%2B-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/Vite-8%2B-646CFF?logo=vite&logoColor=white" alt="Vite 8">
  <img src="https://img.shields.io/badge/Tests-185%20Passed-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/Coverage-81%25-green" alt="Coverage">
  <img src="https://img.shields.io/badge/License-Proprietary-red" alt="License">
</p>

## 📖 Project Overview

**Market Insight Engine (MIE)** is a local-first, modular, high-performance quantitative market data acquisition, technical analysis, and time-series forecasting engine designed for multi-market equities (starting with China A-Share `CN_A` and Hong Kong `CN_HK`, with extensible adapters for global markets).

Quantitative financial engineering frequently suffers from upstream data contamination, inconsistent volume units (lots vs. shares), unrecorded retrospective data revisions, silent task hangs without checkpoint recovery, and opaque front-end/back-end data provenance. MIE addresses these challenges through a strictly decoupled **"Acquire — Validate — Normalize — Store — Analyze — Visualize"** pipeline.

### 🌟 Key Highlights

* **Modular & Decoupled Data Acquisition System (`src/acquisition/`)**:

  * **Strict Separation of Provider & Normalizer Responsibilities**: Providers (`AKShareProvider`, `MockProvider`) fetch raw, unaltered DataFrame/JSON payloads and declare their native volume unit (`LOT` or `SHARE`). `BarNormalizer` serves as the single authority for volume unit conversion and data sanitization, eliminating double-multiplication bugs.

  * **VWAP Geometric & Physical Plausibility Verification**: Validates the intrinsic relationship among turnover amount, volume, and closing price ($\text{ratio} = \frac{\text{amount}}{\text{volume} \times \text{close}}$) prior to normalization to guard against sudden upstream unit shifts.

  * **Production Mock Isolation Gate**: `ProviderRegistry` enforces strict environment boundaries—registering or invoking `MockProvider` in `production` raises a fatal security error immediately.

* **High-Availability Task Persistence & Breakpoint Resumption**:

  * **SQLite WAL Transactional State**: All acquisition tasks and per-symbol subtasks (`acquisition_tasks` and `acquisition_task_items`) are persisted in SQLite with execution latency, row counts, and source interface provenance.

  * **Autonomous Heartbeat & Zombie Task Detection**: Background workers refresh task heartbeats every 5 seconds; stale tasks exceeding 120 seconds without a heartbeat are automatically detected and marked as `INTERRUPTED`.

  * **Breakpoint Resumption & Timeout Circuit Breakers**: Enforces a 15-second per-symbol timeout and a 20-minute batch deadline. Interrupted or partial tasks can be resumed from the exact point of failure, automatically skipping previously completed symbols.

* **High-Throughput Composite Storage Engine (`CompositeStorageEngine`)**:

  * **Apache Parquet**: Atomic temporary-file writes with Zstd compression, row-count verification, and SHA-256/CRC32 checksums.

  * **DuckDB OLAP Engine**: High-concurrency analytical SQL queries directly over local Parquet partitions.

  * **SQLite WAL Metadata & Audit**: Tracks bar coverage ranges, raw payload Gzip archives (`raw_response_audit`), and historical bar revisions (`data_revision_audit`).

* **Point-in-Time Quantitative Analytics & Forecasting**:

  * **Vectorized Technical Indicators**: Powered by Polars for fast computation of `MA`, `EMA`, `MACD`, `RSI`, `KDJ`, `BOLL`, and `ATR`, alongside dynamic forward (`QFQ`) and backward (`HFQ`) corporate-action adjustments.

  * **Anti-Leakage ML Forecasting (`LightGBMPredictor`)**: 13-feature point-in-time pipeline guarded by `DataLeakageGuard` and evaluated via out-of-sample `WalkForwardEvaluator` with A-share long-only and 25 bps transaction friction constraints.

* **Interactive High-DPI Web UI**:

  * Single-screen market terminal built with React 19, TypeScript and a hand-drawn Canvas engine: warm-paper palette, hairline typography, tabular numerals, total page height capped at 1.5 viewports.

  * Fluid root font-size (clamp 12.5→20px) plus a DPR-aware canvas backing store keeps the UI readable and razor sharp from 1024×768 laptops to 4K displays, including 125%/150%/200% system scaling.

  * Includes an interactive `DataUpdateDialog` and a real-time `TaskDrawer` displaying live heartbeats, progress rings, and one-click breakpoint resumption. Design notes: `docs/FRONTEND_REBUILD_V2.md`.

## 🏛️ System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Web UI (React + TypeScript)                     │
│  [Update Data] ──> DataUpdateModal ──> TaskMonitorDrawer (Heartbeat)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP REST
┌───────────────────────────────────▼────────────────────────────────────┐
│                  FastAPI Gateway (/api/v1/acquisition)                 │
│         POST /tasks | GET /tasks/{id} | POST /tasks/{id}/resume        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│      AcquisitionTaskManager (Orchestrator + Resume + Heartbeat Guard)  │
│     - SQLite WAL Persistence (acquisition_tasks / task_items)          │
│     - 5s Async Heartbeat | 120s Zombie Sweep | 20m Hard Timeout        │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
┌───────────────────▼──────────────┐   ┌─────────────▼───────────────────┐
│     AcquisitionService Core      │   │   AcquisitionScheduler (Timer)  │
│  - Raw Gzip Archive (data/raw)   │   │  - A-Share Trading Calendar     │
│  - SQLite Audit (raw_response)   │   │  - 45m Post-Close Release Buffer│
└───────────────────┬──────────────┘   └─────────────────────────────────┘
                    │
┌───────────────────▼────────────────────────────────────────────────────┐
│     ProviderRegistry (Priority Routing / Failover / Prod Mock Gate)    │
└─────────┬────────────────────────────────────────────────────┬─────────┘
          │                                                    │
┌─────────▼────────────────────────┐         ┌─────────────────▼─────────┐
│ AKShareProvider (Raw Fetch Only) │         │ MockProvider (Dev/Test)   │
│ - Fetches raw DataFrame / text   │         │ - Allowed in non-prod only│
│ - Declares volume_unit (LOT/SHR) │         │ - Blocked in production   │
└─────────┬────────────────────────┘         └───────────────────────────┘
          │
┌─────────▼──────────────────────────────────────────────────────────────┐
│        BarNormalizer (Single-Responsibility Normalizer & Validator)    │
│  - Single deterministic conversion: LOT -> * 100 -> SHARE; SHARE -> * 1│
│  - VWAP & Geometric Check: verifies raw_ratio = amount / (vol * close) │
│  - Sanitizes zero-volume halts, price anomalies, and UTC alignment     │
│  - Generates deterministic SHA-256 fingerprint -> Canonical MarketBars │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼──────────────────────────────────────┐
│       CompositeStorageEngine (Atomic Parquet + DuckDB + SQLite WAL)    │
└────────────────────────────────────────────────────────────────────────┘

```

## 📁 Directory Structure

```
Market_Insight_Engine/
├── config/                     # Global application settings & logging configuration
│   ├── __init__.py
│   ├── logging_config.py       # Structured console & rotating file logging
│   └── settings.py             # Pydantic BaseSettings environment management
├── docs/                       # Architecture specifications & verification reports
│   ├── OPERATIONAL_RELIABILITY/# 24 operational reliability test suites
│   ├── STEP7/                  # Modular data acquisition architecture & design specs
│   └── ...
├── scripts/                    # Operations & benchmarking scripts
│   ├── benchmark_resource_usage.py
│   ├── inspect_meta_db.py
│   └── inspect_parquet_volumes.py
├── src/                        # Backend Python source code
│   ├── acquisition/            # [Step 7] Modular market data acquisition & scheduling
│   │   ├── base.py             # Entities: RawProviderResponse, VolumeUnit, etc.
│   │   ├── normalizer.py       # BarNormalizer: deterministic unit scaling & VWAP check
│   │   ├── registry.py         # ProviderRegistry: routing & production mock isolation
│   │   ├── providers/          # Concrete providers (AKShareProvider, MockProvider)
│   │   ├── service.py          # AcquisitionService: orchestration & raw archiving
│   │   ├── task_manager.py     # AcquisitionTaskManager: SQLite state, heartbeat, resume
│   │   ├── scheduler.py        # AcquisitionScheduler: calendar-aware post-close buffer
│   │   └── cli.py              # Standalone CLI entrypoint
│   ├── adapters/               # Legacy & failover data source adapters
│   ├── analysis/               # Vectorized indicators, market breadth & sector rotation
│   ├── api/                    # FastAPI REST gateway
│   │   ├── app.py              # Application factory, CORS & static UI mounting
│   │   └── v1/                 # REST routers (acquisition, market, analysis, prediction, system)
│   ├── core/                   # Canonical domain entities, exceptions & interfaces
│   ├── models/                 # Point-in-time features, leakage guard & LightGBM predictor
│   ├── quality/                # Data quality validator & trading calendar engine
│   └── storage/                # Composite storage engine (Parquet + DuckDB + SQLite WAL)
├── tests/                      # Automated unit & integration test suites
│   ├── conftest.py
│   ├── integration/            # CLI, API, task persistence, heartbeat & recovery tests
│   └── unit/                   # Volume normalization, mock isolation, indicators & ML tests
├── web/                        # Frontend React 19 + TypeScript application
│   ├── src/
│   │   ├── components/         # TopBar, QuoteBoard, ChartWorkspace, ContextRail, InsightDock, TaskDrawer, DataUpdateDialog
│   │   ├── api.ts              # Typed REST API client
│   │   └── types.ts            # Frontend TypeScript interfaces
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── .env.example                # Environment variable template
├── .gitignore                  # Git ignore rules (excludes raw/production data & caches)
├── pyproject.toml              # Python packaging, dependencies, Ruff & Mypy config
├── 报告.md                      # Deployment and model verification report
└── README.md                   # Project documentation

```

## 🚀 Quickstart Guide

### 1. Prerequisites

* **Python**: 3.11 or higher

* **Node.js**: 18.0 or higher (LTS recommended)

* **OS**: Linux / macOS / Windows 10+

### 2. Backend Setup

```
# 1. Clone the repository
git clone <repository_url>
cd Market_Insight_Engine

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows:
.\.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# 3. Install dependencies in editable mode with dev tools
pip install -e ".[dev]"

# 4. Configure environment variables
cp .env.example .env

```

### 3. Frontend Setup

```
cd web

# 1. Install npm dependencies
npm install

# 2. Build production static assets (outputs to web/dist/, mounted by FastAPI)
npm run build
cd ..

# (Optional) Start Vite local development server with hot reload (default port 3000)
# npm run dev

```

### 4. Initial Data Ingestion (Cold Start)

Because historical market data is excluded from Git (zero data-leakage hygiene rule), fetch initial bars for benchmark and securities before launching the web UI:

```
# 1. Probe connectivity across data providers
python -m src.acquisition.cli health

# 2. Ingest initial historical bars
python -m src.acquisition.cli fetch --symbol 600519.SH --timeframe 1d --start 2021-01-01 --end 2024-12-31
python -m src.acquisition.cli fetch --symbol 000001.SH --timeframe 1d --start 2021-01-01 --end 2024-12-31

```

### 5. Running the Application

From the project root directory, launch the FastAPI server:

```
uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

```

* **Web Application UI**: `http://127.0.0.1:8000/ui/` (or root `http://127.0.0.1:8000/` with auto-redirect, or `http://localhost:3000` via Vite dev server)

* **Interactive API Docs (Swagger UI)**: `http://127.0.0.1:8000/docs` (enabled in `development` mode)

* **System Health Probe**: `http://127.0.0.1:8000/api/v1/system/health`

## 💻 Standalone CLI Operations

MIE includes a standalone CLI tool (`src/acquisition/cli.py`) to run data ingestion, health checks, and task maintenance without starting the web server:

```
# 1. Probe connectivity and health across registered data providers
python -m src.acquisition.cli health

# 2. Fetch daily bars for a single security (e.g., Kweichow Moutai 600519.SH)
python -m src.acquisition.cli fetch --symbol 600519.SH --timeframe 1d --start 2023-01-01 --end 2023-12-31

# 3. Run batch acquisition across multiple symbols
python -m src.acquisition.cli batch --symbols 600519.SH,000858.SZ,000001.SZ --timeframe 1d

# 4. Inspect task progress and per-symbol execution breakdown
python -m src.acquisition.cli status --task-id <TASK_ID>

# 5. Resume an interrupted task from its SQLite checkpoint (skips completed symbols)
python -m src.acquisition.cli resume --task-id <TASK_ID>

# 6. Sweep and mark stale/zombie tasks whose heartbeats timed out
python -m src.acquisition.cli cleanup-zombies

```

## 🌐 Core REST API Endpoints

| HTTP Method | Endpoint | Description | 
| ----- | ----- | ----- | 
| **GET** | `/api/v1/system/health` | Liveness probe and service version check | 
| **GET** | `/api/v1/system/info` | Runtime environment, Python version, and storage root metadata | 
| **POST** | `/api/v1/acquisition/tasks` | Create and trigger an asynchronous data acquisition task (single or batch) | 
| **GET** | `/api/v1/acquisition/tasks` | List recent acquisition tasks with optional status filtering | 
| **GET** | `/api/v1/acquisition/tasks/{id}` | Retrieve detailed task progress, heartbeat timestamp, and per-symbol items | 
| **POST** | `/api/v1/acquisition/tasks/{id}/cancel` | Cancel an active running acquisition task | 
| **POST** | `/api/v1/acquisition/tasks/{id}/resume` | Resume an interrupted/failed task from checkpoint (skips `SUCCESS` items) | 
| **POST** | `/api/v1/acquisition/tasks/cleanup-zombies` | Scan and mark stale `RUNNING` tasks (heartbeat older than 120s) as `INTERRUPTED` | 
| **GET** | `/api/v1/acquisition/providers/health` | Probe real-time connectivity of registered upstream providers | 
| **GET** | `/api/v1/market/securities` | Query covered securities metadata list with market/keyword filters | 
| **GET** | `/api/v1/market/quote` | Fetch latest quote snapshot and provenance metadata for a symbol | 
| **GET** | `/api/v1/market/bars` | Query multi-timeframe OHLCV bars (`1d`, `1w`, `1M`, `1Q`, `1Y`) and adjustments (`none`, `qfq`, `hfq`) | 
| **GET** | `/api/v1/analysis/indicators` | Compute vectorized technical indicators (`MA`, `EMA`, `MACD`, `RSI`, `KDJ`, `BOLL`, `ATR`) | 
| **GET** | `/api/v1/analysis/breadth` | Compute cross-sectional market breadth (advancers, decliners, limit-up/down) | 
| **GET** | `/api/v1/analysis/sectors` | Compute sector rotation and relative strength against a benchmark index | 
| **GET** | `/api/v1/analysis/relative-performance` | Compute CAPM Beta, Jensen's Alpha, correlation, and $R^2$ vs. benchmark | 
| **GET** | `/api/v1/prediction/models` | List available statistical baseline and ML prediction models | 
| **GET** | `/api/v1/prediction/forecast` | Generate point-in-time forward return forecast with 80% confidence interval and state probabilities | 
| **GET** | `/api/v1/prediction/walk-forward-report` | Run out-of-sample walk-forward validation with long-only & transaction friction constraints | 

## 🧪 Testing & Quality Verification

```
# 1. Run the full automated test suite (185 tests including 24 operational reliability tests)
pytest tests/ docs/OPERATIONAL_RELIABILITY/

# 2. Run static linting via Ruff
ruff check src tests

# 3. Verify code formatting via Ruff
ruff format --check src tests

# 4. Run strict static type checking via Mypy
mypy src/acquisition src/api/v1/acquisition.py --follow-imports=silent
```

## ⚙️ Configuration Reference

All parameters can be customized in the `.env` file (prefixed with `MIE_`):

| Variable | Default | Description | 
| ----- | ----- | ----- | 
| `MIE_ENV` | `development` | Runtime environment (`development` / `test` / `production`). Mock providers are strictly blocked in `production`. | 
| `MIE_LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | 
| `MIE_HOST` | `127.0.0.1` | Server bind address (defaults to local loopback for security) | 
| `MIE_PORT` | `8000` | Server listen port | 
| `MIE_DATA_ROOT` | `./data` | Root directory for Parquet partitions (`production/`, `staging/`, `quarantine/`, `raw/`) | 
| `MIE_META_DB_PATH` | *(empty)* | Custom SQLite metadata DB path (defaults to `${MIE_DATA_ROOT}/meta.db`) | 
| `MIE_CACHE_MAX_SIZE` | `256` | Maximum entries per in-memory LRU cache namespace | 
| `MIE_CACHE_TTL_SECONDS` | `300` | Time-to-live (seconds) for hot cache entries | 
| `MIE_MAX_WORKER_THREADS` | `4` | Background worker thread pool size | 
| `MIE_MAX_CPU_PERCENT` | `75` | CPU utilization threshold for scheduling new background tasks | 
| `MIE_ENABLE_GPU` | `false` | Enable GPU acceleration for supported models | 

## 🛡️ Data Hygiene & Engineering Principles

1. **Zero Data Leakage in Version Control**: All runtime market data (`data/production/`, `data/raw/`, `*.parquet`, `*.db`) are excluded via `.gitignore` and must never be committed to Git.

2. **Immutable Provenance & Audit Trail**: Every ingested payload is archived with SHA-256 fingerprints (`raw_response_hash` and `normalized_data_hash`) and tracked in `raw_response_audit` and `data_revision_audit`.

3. **Strict Authenticity Transparency**: The UI and API explicitly label data provenance (`real_provider` vs. `synthetic_test`) and never silently substitute synthetic data in production workflows.

4. **Research Disclaimer**: All quantitative indicators, backtests, and machine learning forecasts generated by MIE are strictly for academic and engineering research reference and do not constitute investment advice.