# MIE_V0.70 — Step7 Comprehensive Implementation Plan

**Document ID**: `MIE-STEP7-PLAN-001`  
**Version**: `MIE_V0.70`  
**Status**: `APPROVED WITH USER DIRECTIVES / EXECUTING PHASE 3`  
**Scope**: Detailed Work Breakdown Structure (WBS) for Phase 3 through Phase 9 incorporating the 7 core user directives.

---

## 1. 核心指示融入与执行路线图

根据用户明确指示：
1. **任务状态 SQLite 持久化、心跳与僵尸任务检测 (P0)** -> 落地于 Phase 4 / TaskManager
2. **Provider 与 Normalizer 职责唯一化 (P0)** -> 落地于 Phase 3 / Providers & Normalizer
3. **MockProvider 生产环境隔离 (P0)** -> 落地于 Phase 3 / Registry
4. **成交量只转换一次并验证原始值 (P0)** -> 落地于 Phase 3 / Normalizer
5. **超时、断点恢复与批量任务期限重新设计 (P1)** -> 落地于 Phase 4 & Phase 7
6. **统一基线文件计数 (P2)** -> 已完成于 Phase 0/1 报告
7. **定时更新加入行情发布缓冲 (P2)** -> 落地于 Phase 7 / Scheduler

---

## 2. 阶段执行计划 (WBS: Phase 3 ~ Phase 9)

### Phase 3: 核心 Provider 与 Normalizer 单一职责实施 (Directive 2, 3, 4)
- **子任务**:
  1. 创建 `src/acquisition/base.py`：定义 `BaseProvider`、`VolumeUnit`、`RawProviderResponse`、`VolumeNormalizationSpec`。
  2. 实现 `src/acquisition/normalizer.py`（`BarNormalizer`）：
     - 原始数据检验与 VWAP 合理性比对。
     - 单次确定性转换（东财手乘以 100，新浪股保持 1.0）。
     - 生成带 SHA-256 Checksum 的 `MarketBar`。
  3. 实现 `src/acquisition/registry.py`（`ProviderRegistry`）：
     - 增加环境门禁检查：`production` 环境下严格禁止注册或返回 `MockProvider`。
  4. 实现 `src/acquisition/providers/akshare_provider.py`：
     - Provider 职责唯一化，仅做原始接口拉取与返回，不参与量纲与清洗。
  5. 实现 `src/acquisition/providers/mock_provider.py`。
  6. 编写单元测试：
     - `tests/unit/test_acquisition_providers.py`
     - `tests/unit/test_volume_normalization.py`
     - `tests/unit/test_mock_provider_isolation.py`

### Phase 4: SQLite 任务持久化、心跳守护、断点恢复与 CLI 实施 (Directive 1, 5)
- **子任务**:
  1. 在 `src/storage/sqlite_meta.py` 扩充 `acquisition_tasks` 与 `acquisition_task_items` 表。
  2. 实现 `src/acquisition/task_manager.py`：
     - 任务状态全量 SQLite 持久化。
     - 后台心跳维持循环（5 秒一次）。
     - 僵尸任务自动探测清理（无心跳 > 120 秒）。
     - 断点续传调度（只处理未成功标的）。
     - 单任务 20 分钟超时硬熔断机制。
  3. 实现 `src/acquisition/service.py`：
     - 整合 Provider、Normalizer、Raw 归档（gzip/JSON）与 CompositeStorageEngine。
  4. 实现 `src/acquisition/cli.py`：
     - 提供 `fetch`、`batch`、`resume`、`cleanup-zombies` 命令。
  5. 编写集成测试：
     - `tests/integration/test_acquisition_task_persistence.py`
     - `tests/integration/test_acquisition_standalone_cli.py`

### Phase 5: REST API 路由与网关集成 (Part C)
- **子任务**:
  1. 实现 `src/api/v1/acquisition.py` 路由。
  2. 挂载到 `src/api/app.py`。
  3. 编写集成测试：`tests/integration/test_api_acquisition.py`。

### Phase 6: 前端主动更新面板与实时监控 (Part D)
- **子任务**:
  1. 创建 `web/src/components/DataUpdateModal.tsx` 与 `TaskMonitorDrawer.tsx`。
  2. 集成至 `StockHeader.tsx` 与主界面。
  3. 执行 `npm run build` 确保前端毫秒级纯净构建。

### Phase 7: 日历感知调度器与行情发布缓冲 (Directive 7)
- **子任务**:
  1. 实现 `src/acquisition/scheduler.py`：支持交易日收盘后 45 分钟缓冲触发。
  2. 编写单元测试：`tests/unit/test_acquisition_scheduler.py`。

### Phase 8 & Phase 9: 全量回归、质量验收与正式交付
- **子任务**:
  1. 执行 `pytest` 全量回归套件（132 + 24 + 新增测试）。
  2. 执行 `mypy src --strict` 与 `ruff check .`。
  3. 生成全量验收证据与终验交付报告。
