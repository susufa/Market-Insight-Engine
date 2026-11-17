# MIE 前端重写（beta_ver）— 暖纸终端设计说明与验证报告

> 适用范围：`MIE Beta 0.1.0/beta_ver/web`
> 验证方式：本地无头 Chrome 实测（验收脚本、fixture 与截图属于本地 QA 产物，不随仓库提交）

---

## 1. 重写范围

前端由 6 个大组件 + 1 个页面壳整体重写，旧的组件文件已删除，不再保留双份实现：

| 旧文件 | 新文件 | 职责变化 |
| :--- | :--- | :--- |
| `components/Header.tsx` | `components/TopBar.tsx` | 品牌、指数带、可键盘导航的搜索、网关健康灯 |
| `components/StockHeader.tsx` | `components/QuoteBoard.tsx` | 标的身份 + 大价格 + 6 项盘口指标 + 数据血缘徽标 |
| `components/StockChart.tsx` | `components/ChartWorkspace.tsx` | 重写 Canvas 绘制：右侧价格轴标签、末价标签、十字光标轴标签、DOM 浮窗、DPR 自适应 |
| `components/SecondaryTabs.tsx` | `components/InsightDock.tsx` + `components/ContextRail.tsx` | 五段信息 Dock + 右栏常驻指标面板（≥1440px 显示） |
| `components/DataUpdateModal.tsx` | `components/DataUpdateDialog.tsx` | 采集任务创建弹窗（键盘可关闭、参数摘要） |
| `components/TaskMonitorDrawer.tsx` | `components/TaskDrawer.tsx` | 任务抽屉：进度环、心跳、明细、断点续传 |
| `App.tsx` | `App.tsx`（重写） | 状态编排、指数快照、健康探测、页面占用自检 |
| — | `lib/format.ts`、`hooks/useDisplay.ts` | 统一的数值格式化、尺寸/DPR 监听、弹层行为 |

删除的依赖：`lightweight-charts`（旧版未使用，新图表为自绘 Canvas）。

---

## 2. 设计语言

### 2.1 色彩：与旧版完全一致

沿用原 `index.css` 的暖灰色阶与涨跌色，一个色值都没有改：

| Token | 色值 | 用途 |
| :--- | :--- | :--- |
| warm-50 | `#FAF9F5` | 页面底色（暖纸） |
| warm-100 | `#F5F3EC` | 沉降面 / 分段控件底 |
| warm-200 | `#EAE6DF` | 主分隔线 |
| warm-300 | `#D6D1C6` | 强分隔线 / 滚动条 |
| warm-400 | `#9C978E` | 三级文字 / 轴标签 |
| warm-500 | `#6E6B65` | 次级文字 |
| warm-600 | `#4D4A45` | 正文 |
| warm-700 / 800 / 900 | `#33322F` / `#1F1E1D` / `#121110` | 标题、主按钮、墨色 |
| market-red | `#DC2626` | 涨（A 股口径） |
| market-green | `#16A34A` | 跌（A 股口径） |

新增的两个辅助色只用于图表线条与预测强调，不参与主色板：`#2D6C8E`（青蓝）、`#B4552E`（赭石）、`#9A7B2F`（黄铜）、`#7A7480`（暖灰紫）。

### 2.2 字体与排版

- 品牌字：`Iowan Old Style / Palatino / Cambria` 衬线，仅用于拉丁文标题，制造印刷品质感；
- 中文正文：`Segoe UI Variable Text / PingFang SC / Microsoft YaHei UI`；
- 数字：`Cascadia Mono / SF Mono / JetBrains Mono` + `tabular-nums`，所有价格、百分比、代码列严格等宽对齐；
- 微标签（`.eyebrow`）：0.6rem、字距 0.16em、全大写、暖灰 400，形成“工程图纸”式的分组感；
- 数字全部带 `font-feature-settings: "tnum"`，价格跳动时不会左右抖动。

### 2.3 形体

- 1px 发丝线为唯一的分隔手段（高 DPI 下降为 0.5px），全程不使用粗边框与重投影；
- 卡片圆角 0.72rem、控件 0.42rem，只有一层几乎不可见的阴影（`0 1px 2px rgba(31,30,29,.03)`）；
- 面板结构单一化：一张卡片 = 一条发丝线 + 一块白面，视觉噪声低。

---

## 3. 信息架构与高度约束

页面为“单屏终端”结构，从上到下五段，全部在首屏内完成，不产生整页滚动：

```
TopBar          品牌 · 指数快照 · 搜索 · 网关健康灯 · 刷新
QuoteBoard      标的身份 · 大号价格/涨跌 · 开高低收量额 · 质检/缓存/来源徽标 · 更新/任务
Workspace       ChartWorkspace（自适应 Canvas） + ContextRail（≥1440px 显示）
InsightDock     01 盘口概览 / 02 广度轮动 / 03 相对表现 / 04 预测验证 / 05 数据治理
StatusBar       版本 · 同步时间 · 视口 / DPR / 页面占用量
```

约束实现（关键 CSS 片段）：

```css
html, body, #root { height: 100%; }
body { overflow: hidden; }                     /* 页面本身永不滚动 */

.app-shell { height: 100%; max-height: 150dvh; display: flex; flex-direction: column; }
main { flex: 1; min-height: 0; }               /* 只有中段伸缩 */
.workspace { flex: 1; min-height: 0; }
.chart-stage { flex: 1; min-height: 9rem; }    /* 画布高度由实际盒高决定 */
.dock { height: clamp(11rem, 25vh, 18rem); }   /* 底部信息带固定比例 */

@media (max-height: 34rem) {                    /* 极短窗口才允许滚动，且总高仍 ≤ 1.5 屏 */
  html, body, #root { height: auto; }
  body { overflow-y: auto; }
  .app-shell { height: auto; min-height: 100dvh; max-height: 150dvh; }
}
```

要点：

1. 画布高度不再用 `window.innerHeight × 0.44` 猜测，而是让 `.chart-stage` 占据剩余空间，由 `ResizeObserver` 读取真实盒高后重绘；
2. Dock 内容区 `overflow-y: auto`，任何面板过长都只在 Dock 内部滚动；
3. 右栏 `rail-panel` 铺满 Workspace 高度，底部固定 `rail-footer`，因此永远与图表卡齐平，不会出现半截空白；
4. `StatusBar` 实时显示 `scrollHeight / innerHeight`，可直接看到“页面 × 视口”读数。

---

## 4. 随“显示器画质”缩放

三层机制，全部基于 CSS 逻辑像素，不使用 `transform: scale()`：

### 4.1 流式基准字号（整页 rem 缩放）

```css
:root { font-size: clamp(12.5px, 0.4vw + 8.2px, 20px); }
```

| 视口宽度 | 计算值 | 实际基准 |
| ---: | ---: | ---: |
| 1024 | 11.7 | 12.5px（下限） |
| 1440 | 13.96 | 13.96px |
| 1920 | 15.88 | 15.88px |
| 2560 | 18.44 | 18.44px |
| 3840 | 23.56 | 20px（上限） |

页面内所有尺寸（间距、圆角、字号、控件高度、Dock 高度）都以 `rem` 表达，因此基准字号变化时整页等比放大，而排版比例始终不变。

### 4.2 Canvas 物理像素背板（高 DPI 清晰度）

```ts
const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
canvas.width  = Math.round(cssWidth  * dpr);
canvas.height = Math.round(cssHeight * dpr);
ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
```

- 所有绘图坐标仍按 CSS 像素书写，鼠标命中测试与十字光标同样使用 CSS 像素；
- 通过 `matchMedia('(resolution: Ndppx)')` 监听跨屏移动 / 浏览器缩放导致的 DPR 突变并重绘；
- 十字光标线、网格线统一做 `+0.5` 对齐，避免 1px 线在物理像素上发虚。

### 4.3 发丝线分级

`@media (min-resolution: 1.5dppx)` 时 `--hair: 0.5px`，让分隔线在 Retina / 高 DPI 屏上保持细锐，而不是变成 2–3 个物理像素的粗线。

### 4.4 实测背板分辨率

见第 7 节表格：例如 `3840×2160 @150%` 下画布 CSS 尺寸为 2122×880，背板实际绘制 3183×1320；`1920×1080 @200%` 下背板为 3090×1232。

---

## 5. 交互与可访问性

- 键盘：`Ctrl/⌘ + K` 或 `/` 聚焦搜索；下拉支持 ↑↓ 选择、Enter 确认、Esc 关闭；弹窗与抽屉 Esc 关闭；
- 语义：Dock 使用 `role="tablist" / role="tab" / role="tabpanel"` 并支持 ←→ 切换；弹窗 `aria-modal="true"`、抽屉同；所有图标按钮带 `aria-label`；
- 焦点：统一 `:focus-visible` 墨色描边；打开弹窗后焦点落在首个可操作控件；
- 动效：入场 200–350ms 的淡入位移、比例 0.985 的弹窗缩放、任务进度环 400ms 过渡；`prefers-reduced-motion: reduce` 下全部降为 0.001ms；
- 涨跌配色：`红涨/绿涨` 一键切换并持久化到 `localStorage`，图表、价格、概率条、板块表同步切换。

---

## 6. 数据真实性调整

重写时同步清除了旧前端的硬编码示例数据，避免“界面声明禁止假数据、界面自己却写死假数据”的自相矛盾：

1. 删除“分红送配”表格中的两行写死的除权数据（2024-06-18 / 2023-06-30 等），改为“复权引擎 + 复权公式 + 无事件时不展示示例行”的说明态；
2. 顶部指数由写死的 `DEFAULT_INDICES` 改为并发请求 `/api/v1/market/quote`，取不到数据时显示“未收录”，不再用基准值伪装实时行情；
3. 空库时不绘制任何演示 K 线，只显示“暂无本地真实行情 · 需先执行更新行情”的空态；
4. 质检状态、缓存命中、数据来源、接口名全部来自接口返回，不再在数据缺失时强行标 PASS。

---

## 7. 验证结果（真实无头 Chrome 渲染）

测试浏览器：本机 Chrome（headless new），页面来自生产构建 `web/dist`。
测试方式：在浏览器层拦截 `/api/v1/**` 返回内存 fixture（仅存在于本地验收脚本，不参与打包，也不会进入生产页面），使面板、图表、任务弹层都有内容可看。

| 用例 | 视口 (CSS) | DPR | 基准字号 | 画布 CSS | 画布背板 | 页面高度比 | 横向溢出 | 结论 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1080P 100% | 1920×1080 | 1.0 | 15.88px | 1545×616 | 1545×616 | 1.000 | 无 | PASS |
| 1080P 125% | 1536×864 | 1.25 | 14.34px | 1201×475 | 1501×594 | 1.000 | 无 | PASS |
| 2K 100% | 2560×1440 | 1.0 | 18.44px | 2122×880 | 2122×880 | 1.000 | 无 | PASS |
| 2K 125% | 2048×1152 | 1.25 | 16.39px | 1659×663 | 2074×829 | 1.000 | 无 | PASS |
| 4K 100% | 3840×2160 | 1.0 | 20.00px | 3365×1549 | 3365×1549 | 1.000 | 无 | PASS |
| 4K 150% | 2560×1440 | 1.5 | 18.44px | 2122×880 | 3183×1320 | 1.000 | 无 | PASS |
| 4K 200% | 1920×1080 | 2.0 | 15.88px | 1545×616 | 3090×1232 | 1.000 | 无 | PASS |
| 笔记本 1440 | 1440×900 | 1.0 | 13.96px | 1116×505 | 1116×505 | 1.000 | 无 | PASS |
| 紧凑屏 1280 | 1280×800 | 1.0 | 13.32px | 1250×438 | 1250×438 | 1.000 | 无 | PASS |
| 半屏 1024 | 1024×768 | 1.0 | 12.50px | 1000×423 | 1000×423 | 1.000 | 无 | PASS |
| 极短 600 | 1024×600 | 1.0 | 12.50px | 1000×298 | 1000×298 | 1.000 | 无 | PASS |

补充断言（全部通过）：

- `dockClip = 0`：11 种视口下 Dock 内容均无被裁切（面板内部滚动条不需要出现）；
- `indexClip = 0`：指数带在窄屏按断点隐藏第 4/3/2 个指数，不再出现“18,244.6”这种被切掉一半的数字；
- 控制台错误：fixture 阶段 `0` 条；空库阶段仅 14 条预期的接口 404（用于验证空态，不属于缺陷）。

交互探针（本地验收时自动执行，全部通过）：

| 探针 | 操作 | 结果 |
| :--- | :--- | :--- |
| 滚轮缩放 | 在画布上 wheel -240 | 图例区间文本改变 ✔ |
| 拖拽平移 | 按住向右拖 25% 画布宽度 | 图例区间文本改变（回溯更早区间）✔ |
| 副图切换 | 点击 MACD | 副图图例变为 DIF/DEA/HIST ✔ |
| 涨跌配色 | 点击 红涨 ↔ 绿涨 | 按钮状态与图表配色切换 ✔ |
| 搜索 | 输入“茅台” | 下拉返回 1/24 标的并高亮 ✔ |
| 弹窗 / 抽屉 | 打开后按 Esc | 正常关闭且恢复页面 ✔ |

验收截图共 22 张（11 组分辨率 + 9 个交互状态 + 空库 + 1280 宽度），仅保留在本地，未随仓库提交。

---

## 8. 构建与运行

```bash
cd web
npm ci
npm run dev        # http://127.0.0.1:3000 ，/api 代理到 127.0.0.1:8000
npm run build      # tsc && vite build → web/dist
```

生产构建使用相对路径（vite `base: './'`），因此既可以被 Vite 预览，也可以直接被 FastAPI 的 `/ui` 静态挂载访问（旧构建使用绝对 `/assets`，在 `/ui` 下会 404）。

> 说明：仓库只保留应用代码与设计文档。无头浏览器验收脚本、fixture 行情与截图均属于本地 QA 产物，已在提交前清理，避免把测试数据带进版本库。

---

## 9. 已知限制

1. 目标形态为桌面终端：CSS 宽度小于约 900px 时，右栏隐藏、Dock 变为单列并在内部滚动，不针对移动端手势做专门适配；
2. 极短窗口（高度 < 38rem）会隐藏指标卡片的辅助说明与代码行以保住主数据，属于有意的降级；
3. 弹窗目前只保证 Esc 关闭与初始焦点，未实现完整的焦点陷阱（Tab 循环）；
4. 公司行动事件没有对应 REST 接口，治理页只展示引擎与口径说明，不展示任何示例数据。

---

## 10. 当前前端文件树

```text
web/
├─ index.html                     # 首屏底色 + boot 占位，防止白闪
├─ vite.config.ts                 # base './' + /api 代理
└─ src/
   ├─ App.tsx                     # 状态编排 / 健康探测 / 页面占用自检
   ├─ main.tsx
   ├─ index.css                   # 设计令牌 + 组件类 + 动效 + 响应式/DPI 规则
   ├─ api.ts                      # REST 客户端（新增 /system/health）
   ├─ types.ts                    # 领域类型（新增 IndexQuote / HealthState）
   ├─ lib/format.ts               # 数值 / 百分比 / 份额 / 时间格式化
   ├─ hooks/useDisplay.ts         # useElementSize / useDisplayProfile / useModalBehavior
   └─ components/
      ├─ TopBar.tsx
      ├─ QuoteBoard.tsx
      ├─ ChartWorkspace.tsx
      ├─ ContextRail.tsx
      ├─ InsightDock.tsx
      ├─ DataUpdateDialog.tsx
      └─ TaskDrawer.tsx
```
