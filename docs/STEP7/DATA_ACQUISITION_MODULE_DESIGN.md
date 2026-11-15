# MIE_V0.70 — Modular Data Acquisition Module Technical Design

**Document ID**: `MIE-STEP7-DESIGN-001`  
**Version**: `MIE_V0.70`  
**Status**: `APPROVED / ENHANCED WITH USER DIRECTIVES`  
**Scope**: Technical specifications for SQLite schemas, Provider/Normalizer separation, Mock isolation, single volume conversion, heartbeat/zombie detection, CLI, and API routes.

---

## 1. 数据库持久化表设计 (SQLite Schemas in `meta.db`)

为满足 Directive 1（任务状态 SQLite 持久化、心跳与僵尸任务检测），在 `data/meta.db` 中新增两张专用表：

### 1.1 `acquisition_tasks` 主任务表
```sql
CREATE TABLE IF NOT EXISTS acquisition_tasks (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,                 -- PENDING, RUNNING, SUCCESS, PARTIAL_SUCCESS, FAILED, CANCELLED, INTERRUPTED
    symbols_json TEXT NOT NULL,           -- JSON array of requested symbols
    timeframe TEXT NOT NULL,              -- 1d, 1h, etc.
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    total_symbols INTEGER NOT NULL,
    completed_symbols INTEGER NOT NULL DEFAULT 0,
    failed_symbols INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    last_heartbeat_at TEXT,               -- ISO 8601 UTC timestamp, updated every 5s during run
    error_message TEXT,
    params_json TEXT                      -- Extra options: provider_preference, force_refresh, etc.
);

CREATE INDEX IF NOT EXISTS idx_acq_task_status ON acquisition_tasks(status);
CREATE INDEX IF NOT EXISTS idx_acq_task_heartbeat ON acquisition_tasks(last_heartbeat_at);
```

### 1.2 `acquisition_task_items` 子任务项表（支持断点续传）
```sql
CREATE TABLE IF NOT EXISTS acquisition_task_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,                 -- PENDING, RUNNING, SUCCESS, FAILED, SKIPPED
    row_count INTEGER DEFAULT 0,
    provider_used TEXT,
    source_interface TEXT,
    execution_latency_ms REAL,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY(task_id) REFERENCES acquisition_tasks(task_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_acq_item_task_symbol ON acquisition_task_items(task_id, symbol);
CREATE INDEX IF NOT EXISTS idx_acq_item_status ON acquisition_task_items(status);
```

---

## 2. 职责唯一化契约 (Provider vs Normalizer Separation)

### 2.1 Provider 职责唯一化（仅负责获取原始报文）
Provider 绝不包含任何业务校验、清洗与单位转换，输出原始数据对象 `RawProviderResponse`：
```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import pandas as pd

class VolumeUnit(str, Enum):
    LOT = "lot"       # 手 (1手 = 100股)
    SHARE = "share"   # 股 (标准股数)

@dataclass
class RawProviderResponse:
    symbol: str
    timeframe: str
    raw_df: pd.DataFrame
    raw_payload_text: str          # Original JSON/CSV text for archival
    source_id: str                 # e.g., 'akshare'
    source_interface: str          # e.g., 'akshare:stock_zh_a_daily' or 'akshare:stock_zh_a_hist'
    volume_unit: VolumeUnit        # Provider declares its raw unit: LOT or SHARE
    request_ts: datetime
    response_ts: datetime
    latency_ms: float
    success: bool
    error_message: str = ""
```

### 2.2 Normalizer 职责唯一化（单一归一化与原始值校验）
Normalizer 是全系统中**唯一**执行量纲换算与 `MarketBar` 组装的地方：
```python
@dataclass(frozen=True)
class VolumeNormalizationSpec:
    raw_volume: float
    raw_volume_unit: VolumeUnit
    normalized_volume: float
    normalized_volume_unit: VolumeUnit = VolumeUnit.SHARE
    unit_conversion_factor: float = 1.0
    vwap_ratio: float = 1.0
    is_validated: bool = True

class BarNormalizer:
    @staticmethod
    def normalize_and_validate(
        raw_response: RawProviderResponse,
        expected_symbol: str,
        start: datetime,
        end: datetime,
    ) -> tuple[list[MarketBar], VolumeNormalizationSpec]:
        """
        1. 验证原始数值: volume >= 0, close > 0, amount >= 0.
        2. 校验 VWAP 比率: amount / (raw_volume * close) 是否符合其 volume_unit 声明.
        3. 单次确定性转换: 若为 LOT 则乘 100.0，若为 SHARE 则乘 1.0. 严禁重复计算.
        4. 生成带 SHA-256 Checksum 的 MarketBar.
        """
```

### 2.3 MockProvider 生产环境强隔离 (Directive 3)
```python
class ProviderRegistry:
    def __init__(self, allow_mock: bool = False, environment: str = "production"):
        self._providers = {}
        self._allow_mock = allow_mock
        self._environment = environment.lower()

    def register(self, provider: BaseProvider) -> None:
        if provider.provider_id == "mock":
            if self._environment == "production" or not self._allow_mock:
                raise SecurityError(
                    f"MockProvider registration blocked! Mock is strictly forbidden in {self._environment} environment."
                )
        self._providers[provider.provider_id] = provider
```

---

## 3. 任务管理器与僵尸任务检测设计 (TaskManager & Heartbeat)

### 3.1 状态流转与心跳守护
```python
class AcquisitionTaskManager:
    # 心跳间隔: 5 秒
    HEARTBEAT_INTERVAL_SECONDS = 5.0
    # 僵尸任务超时阈值: 120 秒无心跳视为僵尸
    ZOMBIE_TIMEOUT_SECONDS = 120.0
    # 单任务硬超时规约: 20 分钟 (1200 秒)
    TASK_HARD_TIMEOUT_SECONDS = 1200.0
```

1. **心跳任务**:
   任务启动后，在后台运行 `_heartbeat_loop(task_id)`，每 5 秒在 `acquisition_tasks` 更新 `last_heartbeat_at = datetime.now(UTC).isoformat()`。
2. **僵尸检测与清理 (`cleanup_zombies`)**:
   - 每次服务启动、或定时巡检执行：
     ```sql
     UPDATE acquisition_tasks
     SET status = 'INTERRUPTED',
         error_message = 'Task marked as INTERRUPTED: process lost heartbeat for > 120s'
     WHERE status = 'RUNNING'
       AND datetime(last_heartbeat_at) < datetime('now', '-120 seconds');
     ```
   - 对应未完成的子项也批量更新为 `FAILED` 或 `INTERRUPTED`。
3. **断点恢复 (`resume_task(task_id)`)**:
   - 仅加载该任务下 `status IN ('PENDING', 'FAILED', 'INTERRUPTED')` 的子标的，重新分发执行，跳过已经 `SUCCESS` 的标的。

---

## 4. 定时调度器与发布缓冲设计 (Scheduler with Buffer)

```python
class AcquisitionScheduler:
    def __init__(
        self,
        task_manager: AcquisitionTaskManager,
        market_close_buffer_minutes: int = 45,  # 默认收盘后缓冲 45 分钟 (15:45 触发)
    ):
        self._task_manager = task_manager
        self._buffer_minutes = market_close_buffer_minutes
```
- 检查交易日历（`TradingCalendar.is_trading_day`）：非交易日直接休眠跳过。
- 交易日 15:00 闭市后，进入缓冲等待，直到 `15:00 + buffer_minutes`（例如 15:45）才启动全市场增量同步，确保交易所官方清算数据与各主备数据源完全发布完毕。

---

## 5. REST API 接口设计 (API Specification)

- `POST /api/v1/acquisition/tasks`: 创建新任务（接收 symbols, timeframe, start_date, end_date, force_refresh）。
- `GET /api/v1/acquisition/tasks`: 任务列表与状态分页查询。
- `GET /api/v1/acquisition/tasks/{task_id}`: 获取任务明细与子项状态进度。
- `POST /api/v1/acquisition/tasks/{task_id}/cancel`: 请求优雅取消任务。
- `POST /api/v1/acquisition/tasks/{task_id}/resume`: 断点续传任务。
- `POST /api/v1/acquisition/tasks/cleanup-zombies`: 手动触发僵尸任务清理。
- `GET /api/v1/acquisition/providers/health`: 供应商健康度探测。
