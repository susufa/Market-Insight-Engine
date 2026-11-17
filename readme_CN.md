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

---

## 📖 项目简介 (Project Overview)

**Market Insight Engine (MIE)** 是一个面向中国 A 股及港股市场的**工业级、高性能、模块化量化行情获取、分析与洞察引擎**。

系统旨在解决金融量化开发中常见的数据源污染、成交量单位口径混淆、历史数据缺乏不可篡改审计追踪、系统进程假死或崩溃导致的任务丢失、以及前后端数据不透明等痛点。MIE 建立了严格解耦的“**获取-清洗-规范化-存储-分析-展示**”全链路工程闭环。

### 🌟 核心特性 (Key Highlights)

- **模块化解耦行情获取系统 (`src/acquisition/`)**:
  - **Provider / Normalizer 职责唯一化**: 数据源提供方仅负责拉取原始未修改的 DataFrame/JSON 数据并声明原始成交量单位；规范化器 `BarNormalizer` 独立承担唯一的成交量换算与清洗职责，彻底避免二次重复乘算。
  - **VWAP 几何与物理合理性校验**: 引入成交金额、成交量与收盘价内在比例校验（$\text{ratio} = \frac{\text{amount}}{\text{volume} \times \text{close}}$），实时防御数据源单位突变异常。
  - **生产环境防注入隔离**: `ProviderRegistry` 物理隔离 `MockProvider`，在生产环境下注册或调用假数据提供方将直接触发致命安全拦截。
- **高可用任务持久化与断点续传调度器**:
  - **SQLite WAL 事务持久化**: 所有行情拉取任务及细分标的明细完全由 SQLite 事务表接管，记录执行耗时、网络延时与数据源指纹。
  - **自律心跳与僵尸任务检测**: 后台任务以 5 秒为周期主动刷新心跳，支持 120 秒超时检测与僵尸进程自动打标恢复。
  - **断点续传与超时熔断**: 严格支持单标的 15 秒超时、全批次 20 分钟硬性熔断；从断点恢复时自动跳过已成功标的。
- **高吞吐量复合分层存储 (`CompositeStorageEngine`)**:
  - 底层基于 Apache Parquet 实施分块原子写入与覆写；
  - 基于 DuckDB 提供极速高并发 OLAP 跨表分析查询；
  - 采用 SQLite WAL 模式管理元数据覆盖范围与数据版本审计。
- **交互式 Web 前端与任务监控抽屉**:
  - 基于 React 19 + Vite + TypeScript 构建的单屏行情终端（暖纸配色、发丝线排版、等宽数字），整页高度严格控制在 1.5 个视口以内；
  - 自绘 Canvas K 线：DPR 物理像素背板、价格轴/末价/十字光标标签、MA/EMA/BOLL 叠加与 VOL/MACD/RSI/KDJ/ATR 副图；
  - 提供交互式行情更新弹窗（`DataUpdateDialog`）与实时任务运行抽屉（`TaskDrawer`），支持进度环、心跳脉冲与断点恢复交互；
  - 设计与实测详见 `docs/FRONTEND_REBUILD_V2.md`。

---

## 🏛️ 系统架构 (Architecture Topology)

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Web UI (React 18 + TS)                         │
│  [更新行情] 按钮 ──> DataUpdateModal ──> TaskMonitorDrawer (心跳/进度条)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP REST
┌───────────────────────────────────▼────────────────────────────────────┐
│                  FastAPI Gateway (/api/v1/acquisition)                 │
│         POST /tasks | GET /tasks/{id} | POST /tasks/{id}/resume        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│           AcquisitionTaskManager (调度引擎 + 断点恢复 + 心跳卫士)         │
│     - SQLite WAL 事务持久化 (acquisition_tasks / acquisition_task_items) │
│     - 5s 异步自律心跳 | 120s 僵尸检测 | 20 分钟硬性超时熔断                │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
┌───────────────────▼──────────────┐   ┌─────────────▼───────────────────┐
│     AcquisitionService 核心编排    │   │   AcquisitionScheduler (定时器)   │
│  - 原始响应 Gzip 归档 (data/raw)  │   │  - A 股交易日历感知              │
│  - SQLite 审计 (raw_response_audit│   │  - 盘后 45 分钟行情发布缓冲       │
└───────────────────┬──────────────┘   └─────────────────────────────────┘
                    │
┌───────────────────▼────────────────────────────────────────────────────┐
│      ProviderRegistry (注册中心: 优先级路由 / 降级 / 生产 Mock 隔离)      │
└─────────┬────────────────────────────────────────────────────┬─────────┘
          │                                                    │
┌─────────▼────────────────────────┐         ┌─────────────────▼─────────┐
│ AKShareProvider (纯粹数据拉取)     │         │ MockProvider (离线隔离测试) │
│ - 仅拉取原始 DataFrame / 文本     │         │ - 仅在非生产环境显式允许   │
│ - 仅声明 volume_unit (LOT/SHARE) │         │ - 生产环境注入即刻抛出异常 │
└─────────┬────────────────────────┘         └───────────────────────────┘
          │
┌─────────▼──────────────────────────────────────────────────────────────┐
│        BarNormalizer (单一职责规范化器 & 数据完整性校验)                  │
│  - 严禁双重乘算: LOT (手) -> * 100 -> SHARE (股); SHARE -> * 1.0        │
│  - 几何与 VWAP 合理性校验: 校验 raw_ratio = amount / (vol * close)     │
│  - 数据源清洗: 过滤停牌零成交、价格异常、时序对齐                         │
│  - 生成确定性 SHA-256 指纹 -> 输出规范 MarketBar 集合                  │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼──────────────────────────────────────┐
│       CompositeStorageEngine (原子写入 Parquet + DuckDB + SQLite)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 目录结构 (Directory Structure)

本代码仓库遵循标准 GitHub 开源/生产级工程结构布局，业务数据、构建缓存与虚拟环境已被彻底隔离：

```text
Market_Insight_Engine/
├── config/                     # 全局系统配置与日志管理
│   ├── __init__.py
│   ├── logging_config.py       # 结构化日志输出格式
│   └── settings.py             # 基于 Pydantic 的环境变量管理
├── docs/                       # 核心技术设计文档与测试集
│   └── OPERATIONAL_RELIABILITY/# 运营可靠性测试集（24 项）  
├── scripts/                    # 运维支持与压测脚本
│   ├── benchmark_resource_usage.py # 存储引擎资源基准压测
│   └── ...
├── src/                        # 后端核心源码
│   ├── acquisition/            # [Step7] 模块化行情获取与调度引擎
│   │   ├── base.py             # 核心实体: RawProviderResponse, VolumeUnit 等
│   │   ├── normalizer.py       # BarNormalizer: 单一换算与 VWAP 合理性校验
│   │   ├── registry.py         # ProviderRegistry: 路由中心与生产 Mock 隔离
│   │   ├── providers/          # 具体数据源实现 (AKShareProvider, MockProvider)
│   │   ├── service.py          # AcquisitionService: 获取编排与原始归档
│   │   ├── task_manager.py     # AcquisitionTaskManager: 事务、心跳、断点恢复
│   │   ├── scheduler.py        # AcquisitionScheduler: 交易日历感知与盘后缓冲
│   │   └── cli.py              # 独立 CLI 命令行执行入口
│   ├── adapters/               # 数据源适配器层
│   ├── analysis/               # 技术指标引擎、市场宽度与板块强弱度
│   ├── api/                    # FastAPI REST 网关
│   │   ├── app.py              # 应用主入口与生命周期管理
│   │   └── v1/                 # REST 路由 (acquisition, market, analysis 等)
│   ├── core/                   # 核心领域实体、契约接口与异常定义
│   │   ├── entities.py         # MarketBar, Security, Timeframe 等
│   │   ├── exceptions.py       # 统一结构化业务异常
│   │   └── interfaces/         # 抽象基类 (BaseStorageEngine, BaseProvider 等)
│   ├── models/                 # 预测基准与 ML 预测器
│   ├── quality/                # 数据质量校验器与交易日历引擎
│   └── storage/                # 分层复合存储引擎 (Parquet + DuckDB + SQLite WAL)
├── tests/                      # 自动化测试套件（161 项）
│   ├── conftest.py
│   ├── integration/            # 集成测试 (CLI、API、任务持久化、心跳与断点)
│   └── unit/                   # 单元测试 (成交量换算、Mock 隔离、调度器等)
├── web/                        # 前端 React 19 + TypeScript 工程
│   ├── src/                    # 前端组件、视图、API 与状态模型
│   │   ├── components/         # TopBar / QuoteBoard / ChartWorkspace / InsightDock 等
│   │   ├── api.ts              # REST API 客户端
│   │   └── types.ts            # 前端 TypeScript 接口定义
│   ├── index.html              # HTML 模板
│   ├── package.json            # 前端依赖配置
│   ├── tsconfig.json           # TypeScript 严格配置
│   └── vite.config.ts          # Vite 打包配置
├── .env.example                # 环境变量配置模板
├── .gitignore                  # Git 忽略规则文件
├── pyproject.toml              # Python 构建配置、依赖、Ruff 与 Mypy 规则
├── 报告.md                      # 部署与模型预测功能完整验证报告
└── README.md                   # 项目核心说明文档 (当前文件)
```

---

## 🚀 快速上手 (Quickstart Guide)

### 1. 环境准备 (Prerequisites)
- **Python**: 3.11 及以上版本
- **Node.js**: 18.0 及以上版本 (推荐 LTS)
- **操作系统**: Linux / macOS / Windows 10+

### 2. 后端安装与配置 (Backend Setup)

```bash
# 1. 克隆代码仓库
git clone <repository_url>
cd Market_Insight_Engine

# 2. 创建并激活 Python 虚拟环境
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 3. 安装依赖包（可编辑模式）
pip install -e ".[dev]"

# 4. 配置环境变量
cp .env.example .env
```

### 3. 前端安装与编译 (Frontend Setup)

```bash
cd web

# 1. 安装 npm 依赖
npm install

# 2. 编译生产构建产物（输出至 web/dist/，由 FastAPI 静态托管）
npm run build
cd ..

# （可选）启动前端本地热重载开发服务器（默认监听端口 3000）
# npm run dev
```

### 4. 初始行情同步 (Cold-Start Ingestion)

系统遵循零数据泄露原则（不向代码仓库提交行情数据与数据库文件）。在初次启动 Web 终端前，建议同步初始基准与股票行情（如贵州茅台与上证指数）：

```bash
# 1. 检查数据源可用性
python -m src.acquisition.cli health

# 2. 同步初始标的历史行情数据
python -m src.acquisition.cli fetch --symbol 600519.SH --timeframe 1d --start 2021-01-01 --end 2024-12-31
python -m src.acquisition.cli fetch --symbol 000001.SH --timeframe 1d --start 2021-01-01 --end 2024-12-31
```

### 5. 启动服务 (Running the Application)

在项目根目录下启动 FastAPI 主后端服务：

```bash
# 启动 API 服务（默认监听端口 8000）
uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

- **Web 前端应用**: [http://127.0.0.1:8000/ui/](http://127.0.0.1:8000/ui/)（访问根路径 [http://127.0.0.1:8000](http://127.0.0.1:8000) 自动跳转，或 Vite 开发服务器 [http://localhost:3000](http://localhost:3000)）
- **交互式 API 文档 (Swagger UI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **系统健康探测**: [http://127.0.0.1:8000/api/v1/system/health](http://127.0.0.1:8000/api/v1/system/health)

---

## 💻 命令行工具使用 (CLI Operations)

MIE 提供了功能完备的独立命令行工具，无需启动 Web 服务器即可独立执行所有数据获取与任务调度运维：

```bash
# 1. 检查各数据源网络与可用性状态
python -m src.acquisition.cli health

# 2. 单只股票行情同步（以贵州茅台为例）
python -m src.acquisition.cli fetch --symbol 600519.SH --timeframe 1d --start 2023-01-01 --end 2023-12-31

# 3. 批量多标的并行拉取
python -m src.acquisition.cli batch --symbols 600519.SH,000858.SZ,000001.SZ --timeframe 1d

# 4. 查询任务运行状态与每只股票的明细拆解
python -m src.acquisition.cli status --task-id <TASK_ID>

# 5. 从意外中断处进行断点续传（自动跳过已成功的标的）
python -m src.acquisition.cli resume --task-id <TASK_ID>

# 6. 手动扫描并清理挂起超时的僵尸任务
python -m src.acquisition.cli cleanup-zombies
```

---

## 🌐 核心 REST API 概览 (API Endpoints)

| HTTP 方法 | 接口路径 | 功能描述 |
|:---|:---|:---|
| **POST** | `/api/v1/acquisition/tasks` | 创建并触发异步行情获取任务（支持单股或批量，返回 `task_id`） |
| **GET** | `/api/v1/acquisition/tasks` | 分页查询行情获取任务列表（支持状态过滤） |
| **GET** | `/api/v1/acquisition/tasks/{id}` | 查询指定任务详细信息（包含心跳状态及每只股票的获取状态与耗时） |
| **POST** | `/api/v1/acquisition/tasks/{id}/cancel` | 取消正在运行的任务 |
| **POST** | `/api/v1/acquisition/tasks/{id}/resume` | 从中断点断点恢复任务（跳过已成功标的） |
| **POST** | `/api/v1/acquisition/tasks/cleanup-zombies` | 扫描并清理心跳超时的僵尸任务 |
| **GET** | `/api/v1/acquisition/providers/health` | 实时探测并返回外部数据源连接健康状态 |
| **GET** | `/api/v1/market/bars` | 查询指定标的历史 K 线与技术指标数据 |
| **GET** | `/api/v1/market/securities` | 查询全市场标的覆盖元数据清单 |

---

## 🧪 测试与质量验证 (Testing & Verification)

项目内置了极为严苛的代码规范检查、静态类型推断与跨分辨率回归测试套件：

```bash
# 1. 执行全量自动化测试（185 项全景测试，含 24 项运营可靠性用例）
pytest tests/ docs/OPERATIONAL_RELIABILITY/

# 2. 静态代码分析与 Lint 检查 (Ruff)
ruff check src tests

# 3. 代码格式化校验 (Ruff Format)
ruff format --check src tests

# 4. 严格静态类型检查 (Mypy)
mypy src/acquisition src/api/v1/acquisition.py --follow-imports=silent
```

---

## ⚙️ 核心配置项说明 (Configuration)

在根目录的 `.env` 文件中可自定义调整各项运行参数：

| 参数名称 | 默认值 | 说明 |
|:---|:---|:---|
| `ENV` | `production` | 运行环境（`production` / `development` / `test`），生产环境下禁用 Mock |
| `DATA_ROOT` | `./data` | 复合存储引擎与元数据库根目录 |
| `ALLOW_MOCK_DATA` | `false` | 是否允许使用模拟数据源（仅在非生产环境下有效） |
| `LOG_LEVEL` | `INFO` | 日志输出级别（`DEBUG`, `INFO`, `WARNING`, `ERROR`） |
| `DEFAULT_MARKET` | `CN_A` | 默认标的市场归属（`CN_A`, `CN_HK`） |
| `AKSHARE_RATE_LIMIT_RPS` | `2.0` | 外部 AKShare 请求频控阈值（每秒最大请求数） |

---

## 🛡️ 数据安全与工程守则 (Data Hygiene Rules)

1. **零数据泄露原则**: 任何行情拉取产生的数据文件（`data/production/`、`data/raw/`、`*.db`、`*.duckdb`）均被 `.gitignore` 排除，严禁提交至版本控制系统。
2. **只读基线保护**: 严禁在生产数据写入时直接修改底层归档文件，所有写入均由 `CompositeStorageEngine` 事务保证并留存不可篡改哈希审计。
3. **真实性透明**: 前端界面明确标识数据源属性与接口路径，绝不使用未经标注的合成数据进行回测或展示。
