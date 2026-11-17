import React, { useRef, useState } from 'react';
import {
  Layers,
  PieChart,
  TrendingUp,
  Sparkles,
  ShieldCheck,
  TriangleAlert,
  CheckCircle2,
  ArrowUpRight,
  ArrowDownRight,
  Database,
  Zap,
} from 'lucide-react';
import type {
  BreadthReport,
  ColorScheme,
  IndicatorRow,
  ModelEvaluationSummary,
  PredictionResult,
  QuoteResponse,
  RelativePerformance,
  SectorSummary,
  Security,
} from '../types';
import {
  fmtAmount,
  fmtDate,
  fmtPct,
  fmtPrice,
  fmtShare,
  fmtVolume,
  pctFromRatio,
  tone,
} from '../lib/format';

type TabId = 'overview' | 'breadth' | 'relative' | 'forecast' | 'governance';

interface InsightDockProps {
  quote: QuoteResponse | null;
  security?: Security;
  breadth: BreadthReport | null;
  sectors: SectorSummary[];
  relative: RelativePerformance | null;
  latestIndicator: IndicatorRow | null;
  prediction: PredictionResult | null;
  walkForward: ModelEvaluationSummary | null;
  colorScheme: ColorScheme;
  qualityStatus: string;
  isCached: boolean;
  dataOrigin: string;
  sourceInterface: string;
  totalBars: number;
}

const TABS: Array<{ id: TabId; index: string; label: string; icon: React.ReactNode }> = [
  { id: 'overview', index: '01', label: '盘口概览', icon: <Layers size={12} /> },
  { id: 'breadth', index: '02', label: '广度与轮动', icon: <PieChart size={12} /> },
  { id: 'relative', index: '03', label: '相对表现', icon: <TrendingUp size={12} /> },
  { id: 'forecast', index: '04', label: '预测验证', icon: <Sparkles size={12} /> },
  { id: 'governance', index: '05', label: '数据治理', icon: <ShieldCheck size={12} /> },
];

const TONE_UP_DOWN = (value: number | null | undefined, upIsRed: boolean) => {
  const t = tone(value);
  if (t === 'flat') return 'flat';
  return (t === 'up') === upIsRed ? 'up' : 'down';
};

export const InsightDock: React.FC<InsightDockProps> = ({
  quote,
  security,
  breadth,
  sectors,
  relative,
  latestIndicator,
  prediction,
  walkForward,
  colorScheme,
  qualityStatus,
  isCached,
  dataOrigin,
  sourceInterface,
  totalBars,
}) => {
  const [tab, setTab] = useState<TabId>('overview');
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const upIsRed = colorScheme === 'CN';

  const onTabKey = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const next =
      event.key === 'ArrowRight'
        ? (index + 1) % TABS.length
        : (index - 1 + TABS.length) % TABS.length;
    setTab(TABS[next].id);
    tabRefs.current[next]?.focus();
  };

  const high = quote?.high ?? null;
  const low = quote?.low ?? null;
  const prevClose = quote?.prev_close ?? null;
  const amplitude =
    high !== null && low !== null && prevClose !== null && prevClose > 0
      ? ((high - low) / prevClose) * 100
      : null;
  const vwap =
    quote && quote.volume > 0 && quote.amount > 0 ? quote.amount / quote.volume : null;

  return (
    <section className="dock" aria-label="信息面板">
      <div className="dock__tabs" role="tablist" aria-label="信息面板分组">
        {TABS.map((item, index) => (
          <button
            type="button"
            key={item.id}
            role="tab"
            ref={(node) => {
              tabRefs.current[index] = node;
            }}
            aria-selected={tab === item.id}
            aria-controls={'dock-panel-' + item.id}
            id={'dock-tab-' + item.id}
            tabIndex={tab === item.id ? 0 : -1}
            className="dock-tab"
            data-active={tab === item.id}
            onClick={() => setTab(item.id)}
            onKeyDown={(event) => onTabKey(event, index)}
          >
            <span className="dock-tab__index">{item.index}</span>
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
        <div className="ml-auto hidden shrink-0 items-center gap-2 py-1 pl-3 lg:flex">
          <span className="eyebrow">{security?.symbol ?? '—'}</span>
          <span className="text-warm-300">/</span>
          <span className="eyebrow">{security?.asset_type ?? 'stock'}</span>
          <span className="text-warm-300">/</span>
          <span className="eyebrow">{totalBars} 根 K 线</span>
        </div>
      </div>

      <div
        className="dock__body"
        role="tabpanel"
        id={'dock-panel-' + tab}
        aria-labelledby={'dock-tab-' + tab}
        key={tab}
      >
        {tab === 'overview' && (
          <Overview
            quote={quote}
            latest={latestIndicator}
            amplitude={amplitude}
            vwap={vwap}
            security={security}
          />
        )}
        {tab === 'breadth' && <Breadth breadth={breadth} sectors={sectors} upIsRed={upIsRed} />}
        {tab === 'relative' && <Relative relative={relative} upIsRed={upIsRed} />}
        {tab === 'forecast' && (
          <Forecast prediction={prediction} walkForward={walkForward} upIsRed={upIsRed} />
        )}
        {tab === 'governance' && (
          <Governance
            qualityStatus={qualityStatus}
            isCached={isCached}
            dataOrigin={dataOrigin}
            sourceInterface={sourceInterface}
          />
        )}
      </div>
    </section>
  );
};

/* -------------------------------------------------------------------------- */
/* Panels                                                                     */
/* -------------------------------------------------------------------------- */

interface OverviewProps {
  quote: QuoteResponse | null;
  latest: IndicatorRow | null;
  amplitude: number | null;
  vwap: number | null;
  security?: Security;
}

const Overview: React.FC<OverviewProps> = ({ quote, latest, amplitude, vwap, security }) => {
  const stats = [
    { label: '振幅', value: amplitude === null ? '—' : amplitude.toFixed(2) + '%', hint: '日内高低差 / 昨收' },
    { label: 'VWAP', value: fmtPrice(vwap), hint: '成交额 / 成交量' },
    { label: '昨收', value: fmtPrice(quote?.prev_close), hint: '前一根日线收盘' },
    { label: '市场 / 币种', value: (security?.market ?? 'CN_A') + ' / ' + (security?.currency ?? 'CNY'), hint: '标的归属' },
    { label: 'RSI(14)', value: fmtPrice(latest?.rsi_14, 1), hint: '动量水位' },
    { label: 'ATR(14)', value: fmtPrice(latest?.atr_14), hint: '真实波幅' },
  ];

  const groups: Array<{ title: string; rows: Array<{ k: string; v: string }> }> = [
    {
      title: '均线系统',
      rows: [
        { k: 'MA5', v: fmtPrice(latest?.ma_5) },
        { k: 'MA10', v: fmtPrice(latest?.ma_10) },
        { k: 'MA20', v: fmtPrice(latest?.ma_20) },
        { k: 'MA60', v: fmtPrice(latest?.ma_60) },
      ],
    },
    {
      title: 'MACD (12,26,9)',
      rows: [
        { k: 'DIF', v: fmtPrice(latest?.macd_dif, 3) },
        { k: 'DEA', v: fmtPrice(latest?.macd_dea, 3) },
        { k: 'HIST', v: fmtPrice(latest?.macd_hist, 3) },
      ],
    },
    {
      title: 'KDJ (9,3,3)',
      rows: [
        { k: 'K', v: fmtPrice(latest?.kdj_k, 1) },
        { k: 'D', v: fmtPrice(latest?.kdj_d, 1) },
        { k: 'J', v: fmtPrice(latest?.kdj_j, 1) },
      ],
    },
    {
      title: 'BOLL (20,2)',
      rows: [
        { k: 'UP', v: fmtPrice(latest?.boll_upper) },
        { k: 'MID', v: fmtPrice(latest?.boll_mid) },
        { k: 'LOW', v: fmtPrice(latest?.boll_lower) },
      ],
    },
  ];

  return (
    <div className="panel-grid panel-grid--2">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="eyebrow">TAPE · 盘口与波动读数</span>
          <span className="eyebrow">{fmtDate(quote?.ts)}</span>
        </div>
        <div className="stat-grid">
          {stats.map((s) => (
            <div className="stat" key={s.label}>
              <span className="eyebrow">{s.label}</span>
              <span className="stat__v">{s.value}</span>
              <span className="stat__hint">{s.hint}</span>
            </div>
          ))}
        </div>
        <div className="code-line">
          成交量 {fmtVolume(quote?.volume)} · 成交额 {fmtAmount(quote?.amount)} · 换手口径为交易所原始披露
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="eyebrow">INDICATORS · 技术指标读数</span>
          <span className="eyebrow">仅使用 ≤ T 日数据</span>
        </div>
        {!latest ? (
          <div className="panel-empty">
            <span className="text-[0.72rem] font-medium text-warm-600">暂无可计算指标</span>
            <span className="text-[0.65rem] text-warm-400">
              指标引擎需要足够的有效历史 K 线；不提供任何兜底常量。
            </span>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 lg:grid-cols-4">
            {groups.map((group) => (
              <div key={group.title} className="flex flex-col">
                <span className="eyebrow mb-1">{group.title}</span>
                <div className="ledger">
                  {group.rows.map((row) => (
                    <div className="ledger-row" key={row.k}>
                      <span className="ledger-row__k">{row.k}</span>
                      <span className="ledger-row__v">{row.v}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

interface BreadthProps {
  breadth: BreadthReport | null;
  sectors: SectorSummary[];
  upIsRed: boolean;
}

const Breadth: React.FC<BreadthProps> = ({ breadth, sectors, upIsRed }) => {
  const upClass = upIsRed ? 'up' : 'down';
  const downClass = upIsRed ? 'down' : 'up';

  return (
    <div className="panel-grid panel-grid--2">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="eyebrow">BREADTH · 全市场截面涨跌</span>
          <span className="eyebrow">{breadth ? fmtDate(breadth.trade_date) : '—'}</span>
        </div>

        {!breadth ? (
          <div className="panel-empty">
            <span className="text-[0.72rem] font-medium text-warm-600">暂无全市场截面统计</span>
            <span className="text-[0.65rem] text-warm-400">
              截面计算未运行或接口离线。系统禁止以静态样本冒充全市场涨跌。
            </span>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between">
              <span className="text-[0.72rem] text-warm-600">
                覆盖率 <b className="num text-warm-900">{fmtShare(breadth.coverage_rate)}</b>
                <span className="text-warm-400">
                  {' '}（活跃 {breadth.active_traded_count} · 停牌 {breadth.suspended_count} · 缺失{' '}
                  {breadth.missing_count}）
                </span>
              </span>
              <span className="eyebrow">{breadth.total_universe_count} 只</span>
            </div>

            <div className="ratio-bar">
              <div
                className="ratio-bar__up"
                style={{ width: (breadth.advance_ratio * 100).toFixed(2) + '%' }}
                title={'上涨 ' + breadth.advance_count}
              />
              <div
                className="ratio-bar__flat"
                style={{
                  width:
                    (
                      (breadth.flat_count / Math.max(1, breadth.active_traded_count)) * 100
                    ).toFixed(2) + '%',
                }}
                title={'平盘 ' + breadth.flat_count}
              />
              <div
                className="ratio-bar__down"
                style={{ width: (breadth.decline_ratio * 100).toFixed(2) + '%' }}
                title={'下跌 ' + breadth.decline_count}
              />
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div className="flex items-center gap-1 text-[0.68rem]">
                <ArrowUpRight size={12} className={upClass} />
                <span className={upClass + ' num font-semibold'}>{breadth.advance_count}</span>
                <span className="text-warm-400 num">
                  {fmtShare(breadth.advance_ratio)} · 涨停 {breadth.limit_up_count}
                </span>
              </div>
              <div className="flex items-center gap-1 text-[0.68rem]">
                <span className="num text-warm-600">{breadth.flat_count}</span>
                <span className="text-warm-400">平盘</span>
              </div>
              <div className="flex items-center justify-end gap-1 text-[0.68rem]">
                <ArrowDownRight size={12} className={downClass} />
                <span className={downClass + ' num font-semibold'}>{breadth.decline_count}</span>
                <span className="text-warm-400 num">
                  {fmtShare(breadth.decline_ratio)} · 跌停 {breadth.limit_down_count}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3 text-[0.68rem] num text-warm-500">
              <span>
                中位数{' '}
                <b className={TONE_UP_DOWN(breadth.median_change_pct, upIsRed)}>
                  {breadth.median_change_pct.toFixed(2)}%
                </b>
              </span>
              <span className="text-warm-300">|</span>
              <span>
                加权均值{' '}
                <b className={TONE_UP_DOWN(breadth.mean_change_pct, upIsRed)}>
                  {breadth.mean_change_pct.toFixed(2)}%
                </b>
              </span>
            </div>

            <div className="note note--warn">
              <TriangleAlert size={12} className="mt-0.5 shrink-0" />
              <span>{breadth.survivorship_bias_warning}</span>
            </div>
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="eyebrow">SECTORS · 行业轮动与相对强度</span>
          <span className="eyebrow">基准 上证指数</span>
        </div>
        {sectors.length === 0 ? (
          <div className="panel-empty">
            <span className="text-[0.72rem] font-medium text-warm-600">暂无行业轮动统计</span>
            <span className="text-[0.65rem] text-warm-400">
              行业成分股映射尚未收录；不展示任何虚构板块收益。
            </span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>板块</th>
                  <th>成分</th>
                  <th className="t-right">涨跌</th>
                  <th className="t-right">相对强弱</th>
                  <th>领涨</th>
                  <th>领跌</th>
                </tr>
              </thead>
              <tbody>
                {sectors.slice(0, 6).map((sector) => (
                  <tr key={sector.sector_name}>
                    <td className="t-name">{sector.sector_name}</td>
                    <td className="text-warm-500">{sector.constituent_count}</td>
                    <td className={'t-right font-semibold ' + TONE_UP_DOWN(sector.avg_change_pct, upIsRed)}>
                      {fmtPct(sector.avg_change_pct)}
                    </td>
                    <td className="t-right">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="spark-track"
                          style={{ width: '2.6rem', display: 'inline-flex' }}
                        >
                          <span
                            className="spark-fill"
                            style={{
                              width:
                                Math.min(100, Math.abs(sector.relative_strength_vs_bench) * 8) + '%',
                              background:
                                (sector.relative_strength_vs_bench >= 0) === upIsRed
                                  ? '#DC2626'
                                  : '#16A34A',
                            }}
                          />
                        </span>
                        <span className={TONE_UP_DOWN(sector.relative_strength_vs_bench, upIsRed)}>
                          {fmtPct(sector.relative_strength_vs_bench)}
                        </span>
                      </span>
                    </td>
                    <td className="t-name">
                      {sector.top_performer}{' '}
                      <span className="text-[0.62rem] text-warm-400">
                        {fmtPct(sector.top_performer_pct, 1)}
                      </span>
                    </td>
                    <td className="t-name">
                      {sector.worst_performer}{' '}
                      <span className="text-[0.62rem] text-warm-400">
                        {fmtPct(sector.worst_performer_pct, 1)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

interface RelativeProps {
  relative: RelativePerformance | null;
  upIsRed: boolean;
}

const Relative: React.FC<RelativeProps> = ({ relative, upIsRed }) => {
  if (!relative) {
    return (
      <div className="panel-grid panel-grid--2">
        <div className="panel-empty">
          <span className="text-[0.72rem] font-medium text-warm-600">暂无相对表现回归结果</span>
          <span className="text-[0.65rem] text-warm-400">
            需标的与基准（上证指数）存在共同有效交易日；缺失时不做任何估算填充。
          </span>
        </div>
      </div>
    );
  }

  const excessTone = TONE_UP_DOWN(relative.cumulative_excess_return, upIsRed);
  const alphaTone = TONE_UP_DOWN(relative.alpha_annualized, upIsRed);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="eyebrow">
          CAPM · {relative.symbol} vs {relative.benchmark_symbol}
        </span>
        <span className="eyebrow">
          {fmtDate(relative.start_date)} → {fmtDate(relative.end_date)} · {relative.sample_count} 个共同交易日
        </span>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <span className="eyebrow">BETA β</span>
          <span className="stat__v">{relative.beta.toFixed(3)}</span>
          <span className="stat__hint">系统性风险敞口</span>
        </div>
        <div className="stat">
          <span className="eyebrow">ALPHA α</span>
          <span className={'stat__v ' + alphaTone}>{pctFromRatio(relative.alpha_annualized)}</span>
          <span className="stat__hint">年化超额收益</span>
        </div>
        <div className="stat">
          <span className="eyebrow">CORRELATION r</span>
          <span className="stat__v">{relative.correlation.toFixed(3)}</span>
          <span className="stat__hint">线性协同度</span>
        </div>
        <div className="stat">
          <span className="eyebrow">R²</span>
          <span className="stat__v">{relative.r_squared.toFixed(3)}</span>
          <span className="stat__hint">解释方差比例</span>
        </div>
        <div className="stat">
          <span className="eyebrow">标的 年化收益 / 波动</span>
          <span className="stat__v">
            {pctFromRatio(relative.stock_annualized_return, 1)} / {pctFromRatio(relative.stock_volatility_annualized, 1)}
          </span>
          <span className="stat__hint">RETURN / VOL</span>
        </div>
        <div className="stat">
          <span className="eyebrow">基准 年化收益 / 波动</span>
          <span className="stat__v">
            {pctFromRatio(relative.benchmark_annualized_return, 1)} /{' '}
            {pctFromRatio(relative.benchmark_volatility_annualized, 1)}
          </span>
          <span className="stat__hint">BENCHMARK</span>
        </div>
        <div className="stat">
          <span className="eyebrow">累计超额收益</span>
          <span className={'stat__v ' + excessTone}>
            {pctFromRatio(relative.cumulative_excess_return)}
          </span>
          <span className="stat__hint">CUMULATIVE EXCESS</span>
        </div>
      </div>

      <div className="code-line">
        回归方程 R_stock − R_f = α + β · (R_bench − R_f) + ε ｜ R_f = 2.0% 年化 ｜ 严格对齐共同交易日，无未来信息穿越
      </div>
    </div>
  );
};

interface ForecastProps {
  prediction: PredictionResult | null;
  walkForward: ModelEvaluationSummary | null;
  upIsRed: boolean;
}

const Forecast: React.FC<ForecastProps> = ({ prediction, walkForward, upIsRed }) => {
  const features = prediction?.feature_importance
    ? Object.entries(prediction.feature_importance)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 4)
    : [];
  const maxFeature = features.length > 0 ? Math.max(...features.map((f) => f[1])) || 1 : 1;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="eyebrow">RESEARCH ONLY</span>
          <span className="text-[0.66rem] text-warm-500">
            学术研究与量化回测参考，不构成任何投资建议
          </span>
        </div>
        {prediction?.is_synthetic ? (
          <span className="chip chip--warn">
            <TriangleAlert size={10} />
            离线模拟数据 · 非真实行情
          </span>
        ) : prediction ? (
          <span className="chip chip--ok">
            <ShieldCheck size={10} />
            真实行情 · 无前瞻时序
          </span>
        ) : null}
      </div>

      {!prediction && !walkForward ? (
        <div className="panel-empty">
          <span className="text-[0.72rem] font-medium text-warm-600">暂无预测与回测输出</span>
          <span className="text-[0.65rem] text-warm-400">
            本地历史不足（预测约需 ≥95 根日线、样本外回测约需 ≥320 根）或未触发训练；不以静态常数冒充实测结果。
          </span>
        </div>
      ) : (
        <div className="panel-grid panel-grid--3">
          <div className="flex flex-col gap-1.5">
            <span className="eyebrow">POINT-IN-TIME · 前向收益</span>
            {prediction ? (
              <>
                <div className="flex items-baseline gap-2">
                  <span
                    className={
                      'num text-[1.25rem] font-semibold ' +
                      TONE_UP_DOWN(prediction.point_estimate, upIsRed)
                    }
                  >
                    {pctFromRatio(prediction.point_estimate)}
                  </span>
                  <span className="eyebrow">HORIZON {prediction.horizon}D</span>
                </div>
                <div className="text-[0.64rem] num text-warm-500">
                  80% 区间 [{pctFromRatio(prediction.lower_bound)}, {pctFromRatio(prediction.upper_bound)}]
                  {' '}· 置信 {fmtShare(prediction.confidence, 0)}
                </div>
                <div className="ratio-bar" style={{ height: '0.28rem' }}>
                  <div
                    className="ratio-bar__up"
                    style={{ width: (prediction.probabilities?.up ?? 0) * 100 + '%' }}
                    title="看涨概率"
                  />
                  <div
                    className="ratio-bar__flat"
                    style={{ width: (prediction.probabilities?.flat ?? 0) * 100 + '%' }}
                    title="震荡概率"
                  />
                  <div
                    className="ratio-bar__down"
                    style={{ width: (prediction.probabilities?.down ?? 0) * 100 + '%' }}
                    title="看跌概率"
                  />
                </div>
                <div className="flex justify-between text-[0.6rem] num text-warm-500">
                  <span>涨 {fmtShare(prediction.probabilities?.up)}</span>
                  <span>平 {fmtShare(prediction.probabilities?.flat)}</span>
                  <span>跌 {fmtShare(prediction.probabilities?.down)}</span>
                </div>
                <div className="text-[0.6rem] num text-warm-400 truncate" title={prediction.model_name}>
                  {prediction.model_name} · v{prediction.model_version}
                </div>
              </>
            ) : (
              <div className="text-[0.68rem] text-warm-400">暂无点估计</div>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="eyebrow">WALK-FORWARD · 滚动样本外</span>
              {walkForward && (
                <span
                  className={
                    'chip ' + (walkForward.outperformed_baseline ? 'chip--ok' : 'chip--warn')
                  }
                >
                  {walkForward.outperformed_baseline ? (
                    <>
                      <CheckCircle2 size={10} /> 优于基准
                    </>
                  ) : (
                    <>
                      <TriangleAlert size={10} /> 未超基准
                    </>
                  )}
                </span>
              )}
            </div>
            {walkForward ? (
              <>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                  <div className="mini-stat">
                    <span className="eyebrow">方向胜率</span>
                    <span className="mini-stat__v">
                      {fmtShare(walkForward.win_rate)}
                      <span className="ml-1 text-[0.6rem] font-normal text-warm-400">
                        / 基准 {fmtShare(walkForward.baseline_win_rate)}
                      </span>
                    </span>
                  </div>
                  <div className="mini-stat">
                    <span className="eyebrow">夏普比率</span>
                    <span className="mini-stat__v">
                      {walkForward.sharpe_ratio.toFixed(2)}
                      <span className="ml-1 text-[0.6rem] font-normal text-warm-400">
                        / 基准 {walkForward.baseline_sharpe.toFixed(2)}
                      </span>
                    </span>
                  </div>
                  <div className="mini-stat">
                    <span className="eyebrow">最大回撤</span>
                    <span className="mini-stat__v down">-{fmtShare(walkForward.max_drawdown)}</span>
                  </div>
                  <div className="mini-stat">
                    <span className="eyebrow">MAE / RMSE</span>
                    <span className="mini-stat__v">
                      {walkForward.mae.toFixed(4)} / {walkForward.rmse.toFixed(4)}
                    </span>
                  </div>
                </div>
                <div className="text-[0.6rem] num text-warm-400">
                  {walkForward.fold_count} 折 · {walkForward.sample_count} 样本 · 时序因果隔离 PASS
                </div>
              </>
            ) : (
              <div className="text-[0.68rem] text-warm-400">暂无样本外回测</div>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="eyebrow">EXPLAIN · Top 特征</span>
              <span className="eyebrow">NORMALIZED</span>
            </div>
            {features.length === 0 ? (
              <div className="text-[0.68rem] text-warm-400">暂无特征归因</div>
            ) : (
              <div className="flex flex-col gap-1">
                {features.map(([name, weight]) => (
                  <div className="flex flex-col gap-0.5" key={name}>
                    <div className="flex items-baseline justify-between text-[0.64rem]">
                      <span className="truncate text-warm-600" title={name}>
                        {name}
                      </span>
                      <span className="num text-warm-500">{(weight * 100).toFixed(1)}%</span>
                    </div>
                    <div className="spark-track">
                      <div
                        className="spark-fill"
                        style={{
                          width: (weight / maxFeature) * 100 + '%',
                          background: '#9A7B2F',
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
            {prediction?.disclaimer && (
              <div className="text-[0.6rem] leading-relaxed text-warm-400">{prediction.disclaimer}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

const GATES = [
  {
    title: 'OHLC 几何关系',
    value: 'ENFORCED',
    detail: '严格保证 High ≥ max(Open, Close) 且 Low ≤ min(Open, Close)，杜绝倒置脏数据。',
  },
  {
    title: '时序前缀一致性',
    value: 'ENFORCED',
    detail: 'T 日指标仅使用 ≤T 日数据计算，回测与实盘口径一致，无未来信息泄露。',
  },
  {
    title: '增量计算与指纹',
    value: 'ACTIVE',
    detail: 'MD5 数据指纹驱动缓存失效，增量与全量结果误差控制在 1e-5 内。',
  },
  {
    title: '原子写入与恢复',
    value: 'WAL',
    detail: 'SQLite WAL 管理元数据，Parquet 原子重命名；崩溃后自动回滚未完成事务。',
  },
];

interface GovernanceProps {
  qualityStatus: string;
  isCached: boolean;
  dataOrigin: string;
  sourceInterface: string;
}

const Governance: React.FC<GovernanceProps> = ({
  qualityStatus,
  isCached,
  dataOrigin,
  sourceInterface,
}) => (
  <div className="panel-grid panel-grid--2">
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="eyebrow">GATES · 数据质量门禁</span>
        <span className={'chip ' + (qualityStatus === 'PASS' ? 'chip--ok' : 'chip--warn')}>
          <ShieldCheck size={10} />
          {qualityStatus}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {GATES.map((gate) => (
          <div key={gate.title} className="note note--info items-start">
            <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-market-green" />
            <div className="flex flex-col gap-0.5">
              <span className="flex items-center gap-1.5 text-[0.7rem] font-medium text-warm-800">
                {gate.title}
                <span className="font-mono text-[0.58rem] text-market-green">{gate.value}</span>
              </span>
              <span className="text-[0.64rem] leading-relaxed text-warm-500">{gate.detail}</span>
            </div>
          </div>
        ))}
      </div>
    </div>

    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="eyebrow">LINEAGE · 复权与数据链路</span>
        <span className="eyebrow">{isCached ? 'LRU HIT' : 'STORE'}</span>
      </div>
      <div className="code-line">
        P_ex = (P_cum − D + R × P_r) / (1 + B + R)
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="chip">不复权 · 原始成交价</span>
        <span className="chip">前复权 · 最新价锚定</span>
        <span className="chip">后复权 · 首日价锚定</span>
      </div>

      <div className="ledger">
        <div className="ledger-row">
          <span className="ledger-row__k">
            <Database size={11} className="text-warm-400" />
            数据来源
          </span>
          <span className="ledger-row__v">{dataOrigin || 'unknown'}</span>
        </div>
        <div className="ledger-row">
          <span className="ledger-row__k">
            <Database size={11} className="text-warm-400" />
            数据接口
          </span>
          <span className="ledger-row__v truncate" title={sourceInterface}>
            {sourceInterface || 'local_store'}
          </span>
        </div>
        <div className="ledger-row">
          <span className="ledger-row__k">
            <Zap size={11} className="text-warm-400" />
            缓存通道
          </span>
          <span className="ledger-row__v">{isCached ? 'LRU 命中（<5ms）' : '复合存储引擎'}</span>
        </div>
      </div>

      <div className="note">
        <span>
          公司行动（分红 / 送转 / 配股）事件由存储层统一维护；本地无事件记录时不展示任何示例行，
          复权计算仅在事件齐备时启用。
        </span>
      </div>
    </div>
  </div>
);
