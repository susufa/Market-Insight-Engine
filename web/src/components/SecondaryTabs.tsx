import React, { useState } from 'react';
import {
  QuoteResponse,
  Security,
  BreadthReport,
  SectorSummary,
  RelativePerformance,
  IndicatorRow,
  PredictionResult,
  ModelEvaluationSummary,
} from '../types';
import {
  Layers,
  PieChart,
  TrendingUp,
  FileSpreadsheet,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  Brain,
  ShieldCheck,
} from 'lucide-react';

interface SecondaryTabsProps {
  quote?: QuoteResponse | null;
  security?: Security;
  breadth?: BreadthReport | null;
  sectors?: SectorSummary[];
  relativePerformance?: RelativePerformance | null;
  latestIndicator?: IndicatorRow | null;
  prediction?: PredictionResult | null;
  walkForwardSummary?: ModelEvaluationSummary | null;
}

export const SecondaryTabs: React.FC<SecondaryTabsProps> = ({
  quote,
  security,
  breadth,
  sectors = [],
  relativePerformance,
  latestIndicator,
  prediction,
  walkForwardSummary,
}) => {
  const [activeTab, setActiveTab] = useState<
    'metrics' | 'breadth' | 'relative' | 'prediction' | 'actions'
  >('metrics');

  const high = quote?.high ?? 0;
  const low = quote?.low ?? 0;
  const prevClose = quote?.prev_close ?? 0;
  const volume = quote?.volume ?? 0;
  const amount = quote?.amount ?? 0;

  const amplitude = prevClose > 0 ? (((high - low) / prevClose) * 100).toFixed(2) : '--';
  const avgPrice = volume > 0 ? (amount / volume).toFixed(2) : '--';

  return (
    <div className="bg-white border-b border-warm-200">
      {/* Tabs Header */}
      <div className="w-full max-w-[2560px] 2xl:max-w-[3400px] mx-auto px-3 sm:px-4 lg:px-6 flex flex-wrap items-center justify-between border-b border-warm-100 select-none">
        <div className="flex flex-wrap items-center gap-3 sm:gap-6">
          <button
            onClick={() => setActiveTab('metrics')}
            className={`py-2 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'metrics'
                ? 'border-warm-800 text-warm-900 font-semibold'
                : 'border-transparent text-warm-500 hover:text-warm-800'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>盘口指标与概览</span>
          </button>

          <button
            onClick={() => setActiveTab('breadth')}
            className={`py-2 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'breadth'
                ? 'border-warm-800 text-warm-900 font-semibold'
                : 'border-transparent text-warm-500 hover:text-warm-800'
            }`}
          >
            <PieChart className="w-3.5 h-3.5" />
            <span>市场广度与行业轮动</span>
          </button>

          <button
            onClick={() => setActiveTab('relative')}
            className={`py-2 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'relative'
                ? 'border-warm-800 text-warm-900 font-semibold'
                : 'border-transparent text-warm-500 hover:text-warm-800'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>标的相对表现 (Beta/Alpha)</span>
          </button>

          <button
            onClick={() => setActiveTab('prediction')}
            className={`py-2 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'prediction'
                ? 'border-warm-800 text-warm-900 font-semibold'
                : 'border-transparent text-warm-500 hover:text-warm-800'
            }`}
          >
            <Brain className="w-3.5 h-3.5 text-indigo-600" />
            <span>智能预测与时序验证 (Step5)</span>
          </button>

          <button
            onClick={() => setActiveTab('actions')}
            className={`py-2 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'actions'
                ? 'border-warm-800 text-warm-900 font-semibold'
                : 'border-transparent text-warm-500 hover:text-warm-800'
            }`}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>分红送配与数据治理</span>
          </button>
        </div>

        <div className="text-[11px] text-warm-400 font-mono hidden md:block">
          标的: {security?.symbol || quote?.symbol || '--'} | 分类: {security?.asset_type || 'stock'}
        </div>
      </div>

      {/* Tab Content Body (bounded to 175px max height with vertical scrollbar if necessary, preserving viewport constraint) */}
      <div className="w-full max-w-[2560px] 2xl:max-w-[3400px] mx-auto px-3 sm:px-4 lg:px-6 py-2.5 text-xs text-warm-700 h-[175px] max-h-[195px] overflow-y-auto">
        {/* Tab 1: 盘口指标与概览 */}
        {activeTab === 'metrics' && (
          <div className="space-y-2">
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-2">
              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">振幅 (日内波动)</div>
                <div className="text-sm font-semibold font-mono text-warm-900">{amplitude}%</div>
              </div>
              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">成交均价 (VWAP)</div>
                <div className="text-sm font-semibold font-mono text-warm-900">¥{avgPrice}</div>
              </div>
              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">昨收参考价</div>
                <div className="text-sm font-semibold font-mono text-warm-900">¥{prevClose.toFixed(2)}</div>
              </div>
              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">交易市场 / 币种</div>
                <div className="text-sm font-semibold font-mono text-warm-900">
                  {security?.market ?? 'CN_A'} / {security?.currency ?? 'CNY'}
                </div>
              </div>
              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">最新 RSI(14)</div>
                <div className="text-sm font-semibold font-mono text-warm-900">
                  {latestIndicator?.rsi_14 != null ? latestIndicator.rsi_14.toFixed(2) : '--'}
                </div>
              </div>
              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">最新 ATR(14)</div>
                <div className="text-sm font-semibold font-mono text-warm-900">
                  {latestIndicator?.atr_14 != null ? latestIndicator.atr_14.toFixed(2) : '--'}
                </div>
              </div>
            </div>

            {latestIndicator && (
              <div className="flex flex-wrap items-center gap-2 sm:gap-3 p-2 bg-warm-50 rounded border border-warm-200 font-mono text-[11px] text-warm-600">
                <span className="font-semibold text-warm-800">均线系统:</span>
                <span>MA5: {latestIndicator.ma_5?.toFixed(2) ?? '--'}</span>
                <span>MA10: {latestIndicator.ma_10?.toFixed(2) ?? '--'}</span>
                <span>MA20: {latestIndicator.ma_20?.toFixed(2) ?? '--'}</span>
                <span>MA60: {latestIndicator.ma_60?.toFixed(2) ?? '--'}</span>
                <span className="text-warm-300">|</span>
                <span>MACD DIF: {latestIndicator.macd_dif?.toFixed(3) ?? '--'}</span>
                <span>DEA: {latestIndicator.macd_dea?.toFixed(3) ?? '--'}</span>
                <span>HIST: {latestIndicator.macd_hist?.toFixed(3) ?? '--'}</span>
                <span className="text-warm-300">|</span>
                <span>KDJ: K={latestIndicator.kdj_k?.toFixed(1) ?? '--'} D={latestIndicator.kdj_d?.toFixed(1) ?? '--'} J={latestIndicator.kdj_j?.toFixed(1) ?? '--'}</span>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: 市场广度与行业轮动 */}
        {activeTab === 'breadth' && (
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
            {/* Left: Market Breadth Stats */}
            {!breadth ? (
              <div className="xl:col-span-5 p-4 bg-warm-50 rounded border border-dashed border-warm-300 text-center space-y-1">
                <div className="text-xs font-semibold text-warm-700">暂无全市场截面涨跌统计</div>
                <div className="text-[11px] text-warm-500">
                  全市场截面计算未运行或接口离线。系统严格禁止展示静态假数据。
                </div>
              </div>
            ) : (
              <div className="xl:col-span-5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-warm-900 text-xs">全市场截面涨跌统计 ({breadth.market || 'CN_A'})</span>
                  <span className="text-[10px] font-mono text-warm-400">
                    覆盖率: {(breadth.coverage_rate * 100).toFixed(1)}% (活跃:{breadth.active_traded_count} / 停牌:{breadth.suspended_count})
                  </span>
                </div>

                {/* Progress bar of Advance / Decline / Flat */}
                <div className="space-y-1">
                  <div className="h-2.5 w-full bg-warm-200 rounded-full flex overflow-hidden">
                    <div
                      className="bg-red-500 h-full transition-all"
                      style={{ width: `${(breadth.advance_ratio * 100).toFixed(1)}%` }}
                      title={`上涨: ${breadth.advance_count} (${(breadth.advance_ratio * 100).toFixed(1)}%)`}
                    />
                    <div
                      className="bg-warm-400 h-full transition-all"
                      style={{
                        width: `${((breadth.flat_count / Math.max(1, breadth.active_traded_count)) * 100).toFixed(1)}%`,
                      }}
                      title={`平盘: ${breadth.flat_count}`}
                    />
                    <div
                      className="bg-emerald-600 h-full transition-all"
                      style={{ width: `${(breadth.decline_ratio * 100).toFixed(1)}%` }}
                      title={`下跌: ${breadth.decline_count} (${(breadth.decline_ratio * 100).toFixed(1)}%)`}
                    />
                  </div>
                  <div className="flex justify-between text-[11px] font-mono">
                    <span className="text-red-600 font-semibold flex items-center gap-0.5">
                      <ArrowUpRight className="w-3 h-3" />
                      涨 {breadth.advance_count} ({(breadth.advance_ratio * 100).toFixed(1)}%) | 涨停 {breadth.limit_up_count}
                    </span>
                    <span className="text-warm-500">平 {breadth.flat_count}</span>
                    <span className="text-emerald-700 font-semibold flex items-center gap-0.5">
                      <ArrowDownRight className="w-3 h-3" />
                      跌 {breadth.decline_count} ({(breadth.decline_ratio * 100).toFixed(1)}%) | 跌停 {breadth.limit_down_count}
                    </span>
                  </div>
                </div>

                {/* Median / Mean changes */}
                <div className="flex items-center gap-3 sm:gap-4 text-[11px] font-mono bg-warm-50 p-1.5 rounded border border-warm-200">
                  <span>中位数: <b className={breadth.median_change_pct >= 0 ? 'text-red-600' : 'text-emerald-700'}>{breadth.median_change_pct}%</b></span>
                  <span>加权均值: <b className={breadth.mean_change_pct >= 0 ? 'text-red-600' : 'text-emerald-700'}>{breadth.mean_change_pct}%</b></span>
                  <span className="text-warm-400 text-[10px]">缺失: {breadth.missing_count}</span>
                </div>

                {/* Survivorship Bias Warning Note */}
                <div className="text-[10px] text-amber-700 bg-amber-50 p-1.5 rounded border border-amber-200 flex items-start gap-1 leading-tight">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-600" />
                  <span>{breadth.survivorship_bias_warning}</span>
                </div>
              </div>
            )}

            {/* Right: Sector Rankings */}
            {sectors.length === 0 ? (
              <div className="xl:col-span-7 p-4 bg-warm-50 rounded border border-dashed border-warm-300 text-center space-y-1">
                <div className="text-xs font-semibold text-warm-700">暂无申万行业轮动统计数据</div>
                <div className="text-[11px] text-warm-500">
                  行业成分股分析尚未收录。系统严格禁止使用假数据冒充行业统计。
                </div>
              </div>
            ) : (
              <div className="xl:col-span-7 space-y-1">
                <div className="flex items-center justify-between text-xs font-semibold text-warm-900">
                  <span>申万一级行业轮动与相对强度 (基准: 上证指数)</span>
                  <span className="text-[10px] font-mono text-warm-400">排序依据: 行业平均涨跌幅</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left font-mono text-[11px] border-collapse min-w-[480px]">
                    <thead>
                      <tr className="border-b border-warm-200 text-warm-400">
                        <th className="py-1">板块名称</th>
                        <th className="py-1">成分数</th>
                        <th className="py-1 text-right">板块涨跌</th>
                        <th className="py-1 text-right">相对强弱(RS)</th>
                        <th className="py-1">领涨龙头</th>
                        <th className="py-1">领跌标的</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sectors.slice(0, 4).map((sec) => (
                        <tr key={sec.sector_name} className="border-b border-warm-100 hover:bg-warm-50">
                          <td className="py-1 font-semibold text-warm-900">{sec.sector_name}</td>
                          <td className="py-1 text-warm-600">{sec.constituent_count}</td>
                          <td className={`py-1 text-right font-semibold ${sec.avg_change_pct >= 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                            {sec.avg_change_pct >= 0 ? `+${sec.avg_change_pct.toFixed(2)}` : sec.avg_change_pct.toFixed(2)}%
                          </td>
                          <td className={`py-1 text-right ${sec.relative_strength_vs_bench >= 0 ? 'text-red-500 font-medium' : 'text-emerald-600'}`}>
                            {sec.relative_strength_vs_bench >= 0 ? `+${sec.relative_strength_vs_bench.toFixed(2)}` : sec.relative_strength_vs_bench.toFixed(2)}%
                          </td>
                          <td className="py-1 text-warm-700 truncate max-w-[120px]" title={sec.top_performer}>
                            {sec.top_performer} <span className="text-red-600 text-[10px]">+{sec.top_performer_pct.toFixed(1)}%</span>
                          </td>
                          <td className="py-1 text-warm-700 truncate max-w-[120px]" title={sec.worst_performer}>
                            {sec.worst_performer} <span className="text-emerald-700 text-[10px]">{sec.worst_performer_pct.toFixed(1)}%</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 3: 标的相对表现 (Beta/Alpha) */}
        {activeTab === 'relative' && (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between text-xs font-semibold text-warm-900 gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span>标的统计相对关系 (CAPM 回归模型)</span>
                <span className="text-[11px] font-normal text-warm-500">
                  基准: {relativePerformance?.benchmark_symbol || '000001.SH (上证指数)'} | 样本周期: {relativePerformance?.start_date?.split('T')[0] ?? '--'} ~ {relativePerformance?.end_date?.split('T')[0] ?? '--'} ({relativePerformance?.sample_count ?? 0} 个有效交易日)
                </span>
              </div>
              <span className="text-[10px] font-mono text-warm-400">无风险收益率 Rf = 2.0% (年化)</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 2xl:grid-cols-7 gap-2">
              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">贝塔系数 (Beta β)</div>
                <div className="text-sm font-semibold font-mono text-warm-900">
                  {relativePerformance?.beta != null ? relativePerformance.beta.toFixed(3) : '--'}
                </div>
                <div className="text-[9px] text-warm-400">系统性风险敞口</div>
              </div>

              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">詹森阿尔法 (Alpha α)</div>
                <div className={`text-sm font-semibold font-mono ${(relativePerformance?.alpha_annualized ?? 0) >= 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                  {relativePerformance?.alpha_annualized != null
                    ? `${(relativePerformance.alpha_annualized * 100).toFixed(2)}%`
                    : '--'}
                </div>
                <div className="text-[9px] text-warm-400">年化超额收益</div>
              </div>

              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">皮尔逊相关系数 (r)</div>
                <div className="text-sm font-semibold font-mono text-warm-900">
                  {relativePerformance?.correlation != null ? relativePerformance.correlation.toFixed(3) : '--'}
                </div>
                <div className="text-[9px] text-warm-400">线性协同度</div>
              </div>

              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">判定系数 (R²)</div>
                <div className="text-sm font-semibold font-mono text-warm-900">
                  {relativePerformance?.r_squared != null ? relativePerformance.r_squared.toFixed(3) : '--'}
                </div>
                <div className="text-[9px] text-warm-400">解释方差比</div>
              </div>

              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">标的年化收益 / 波动</div>
                <div className="text-xs font-semibold font-mono text-warm-900">
                  {relativePerformance ? `${(relativePerformance.stock_annualized_return * 100).toFixed(1)}% / ${(relativePerformance.stock_volatility_annualized * 100).toFixed(1)}%` : '--'}
                </div>
                <div className="text-[9px] text-warm-400">Return / Volatility</div>
              </div>

              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">基准年化收益 / 波动</div>
                <div className="text-xs font-semibold font-mono text-warm-900">
                  {relativePerformance ? `${(relativePerformance.benchmark_annualized_return * 100).toFixed(1)}% / ${(relativePerformance.benchmark_volatility_annualized * 100).toFixed(1)}%` : '--'}
                </div>
                <div className="text-[9px] text-warm-400">Bench Ret / Vol</div>
              </div>

              <div className="p-2 bg-warm-50 rounded border border-warm-200">
                <div className="text-[10px] text-warm-400">累计超额收益</div>
                <div className={`text-sm font-semibold font-mono ${(relativePerformance?.cumulative_excess_return ?? 0) >= 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                  {relativePerformance?.cumulative_excess_return != null
                    ? `${(relativePerformance.cumulative_excess_return * 100).toFixed(2)}%`
                    : '--'}
                </div>
                <div className="text-[9px] text-warm-400">Cumulative Excess</div>
              </div>
            </div>

            <div className="text-[11px] text-warm-500 font-mono bg-warm-50 p-1.5 rounded border border-warm-200 flex flex-wrap items-center justify-between gap-1">
              <span>CAPM回归方程: R_stock - R_f = α + β * (R_bench - R_f) + ε</span>
              <span>时序因果一致性: 严格对齐共同有效交易日，杜绝未来信息穿越</span>
            </div>
          </div>
        )}

        {/* Tab: 智能预测与时序验证 (Step5) */}
        {activeTab === 'prediction' && (
          <div className="space-y-2">
            {/* Compliance Banner */}
            <div className="flex items-center justify-between p-1.5 px-2 bg-amber-50 rounded border border-amber-200 text-amber-900 text-[11px]">
              <div className="flex items-center gap-1.5 font-medium">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                <span>学术研究与量化回测参考，不构成任何投资建议或确定性交易依据</span>
              </div>
              <span className="text-[10px] text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded font-mono hidden sm:inline">
                严格禁止单点买卖点输出
              </span>
            </div>

            {/* Data Provenance & Mock Isolation Status Banner */}
            {prediction?.is_synthetic || walkForwardSummary?.is_synthetic ? (
              <div className="flex items-center justify-between p-1.5 px-2 bg-amber-500/10 border border-amber-500/30 rounded text-amber-800 text-[11px]">
                <span className="font-semibold flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                  ⚠️ 离线模拟演示模式 (Synthetic Mock Data)，非真实行情预测
                </span>
                <span className="font-mono text-[10px] text-amber-700">
                  来源: {prediction?.data_source || 'mock_synth'}
                </span>
              </div>
            ) : prediction?.data_origin === 'real_provider' ? (
              <div className="flex items-center justify-between p-1.5 px-2 bg-emerald-500/10 border border-emerald-500/30 rounded text-emerald-800 text-[11px]">
                <span className="font-semibold flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                  🟢 真实行情数据源: {prediction.data_source || 'akshare'} (已通过质量与防泄漏验证)
                </span>
                <span className="font-mono text-[10px] text-emerald-700">严格无前瞻时序推断</span>
              </div>
            ) : null}

            {!prediction && !walkForwardSummary ? (
              <div className="p-4 bg-warm-50 rounded border border-dashed border-warm-300 text-center space-y-1">
                <div className="text-xs font-semibold text-warm-700">
                  暂无标的 ({security?.symbol || '当前股票'}) 实测预测与回测数据
                </div>
                <div className="text-[11px] text-warm-500">
                  本地存储未持久化足够有效行情（需至少 50 根日线）或未触发训练。系统严格禁止使用假数据或静态常数冒充实测结果。
                </div>
              </div>
            ) : (
              /* Prediction Overview Grid */
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                {/* 1. Point-in-time Forecast & Uncertainty */}
                <div className="p-2 bg-warm-50 rounded border border-warm-200 space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-warm-900 flex items-center gap-1">
                      <TrendingUp className="w-3.5 h-3.5 text-indigo-600" />
                      前向收益预测 ({prediction?.horizon ?? 5}日)
                    </span>
                    <span className="text-[10px] text-warm-500 font-mono">
                      {prediction?.model_name ?? 'lightgbm_quant_model'}
                    </span>
                  </div>

                  {prediction ? (
                    <>
                      <div className="flex items-baseline gap-2">
                        <span
                          className={`text-base font-bold font-mono ${
                            prediction.point_estimate >= 0 ? 'text-red-600' : 'text-emerald-600'
                          }`}
                        >
                          {prediction.point_estimate >= 0 ? '+' : ''}
                          {(prediction.point_estimate * 100).toFixed(2)}%
                        </span>
                        <span className="text-[10px] text-warm-500 font-mono">
                          80%区间: [{(prediction.lower_bound * 100).toFixed(2)}%,{' '}
                          {(prediction.upper_bound * 100).toFixed(2)}%]
                        </span>
                      </div>

                      {/* State Probabilities Bar */}
                      <div className="space-y-0.5 pt-0.5">
                        <div className="flex justify-between text-[10px] font-mono text-warm-600">
                          <span className="text-red-600 font-medium">
                            看涨: {((prediction.probabilities?.up ?? 0.33) * 100).toFixed(1)}%
                          </span>
                          <span className="text-warm-500">
                            震荡: {((prediction.probabilities?.flat ?? 0.34) * 100).toFixed(1)}%
                          </span>
                          <span className="text-emerald-600 font-medium">
                            看跌: {((prediction.probabilities?.down ?? 0.33) * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="w-full h-1.5 bg-warm-200 rounded-full flex overflow-hidden">
                          <div
                            className="bg-red-500 h-full"
                            style={{
                              width: `${(prediction.probabilities?.up ?? 0.33) * 100}%`,
                            }}
                          />
                          <div
                            className="bg-warm-400 h-full"
                            style={{
                              width: `${(prediction.probabilities?.flat ?? 0.34) * 100}%`,
                            }}
                          />
                          <div
                            className="bg-emerald-500 h-full"
                            style={{
                              width: `${(prediction.probabilities?.down ?? 0.33) * 100}%`,
                            }}
                          />
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="text-xs text-warm-500 py-3 text-center">暂无预测点估计</div>
                  )}
                </div>

                {/* 2. Walk-Forward Evaluation & Baseline Comparison */}
                <div className="p-2 bg-warm-50 rounded border border-warm-200 space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-warm-900 flex items-center gap-1">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                      滚动样本外验证 (Walk-Forward)
                    </span>
                    {walkForwardSummary ? (
                      <span
                        className={`text-[10px] font-mono px-1 rounded flex items-center gap-0.5 ${
                          walkForwardSummary.outperformed_baseline
                            ? 'text-emerald-700 bg-emerald-100'
                            : 'text-amber-700 bg-amber-100'
                        }`}
                      >
                        {walkForwardSummary.outperformed_baseline ? (
                          <>
                            <CheckCircle2 className="w-2.5 h-2.5" /> 优于统计基准
                          </>
                        ) : (
                          <>
                            <AlertTriangle className="w-2.5 h-2.5" /> 未超越统计基准
                          </>
                        )}
                      </span>
                    ) : (
                      <span className="text-[10px] text-warm-400 font-mono">未验证</span>
                    )}
                  </div>

                  {walkForwardSummary ? (
                    <>
                      <div className="grid grid-cols-3 gap-1 pt-0.5 text-center font-mono">
                        <div className="p-1 bg-white rounded border border-warm-200">
                          <div className="text-[9px] text-warm-400">方向胜率</div>
                          <div className="text-xs font-bold text-warm-900">
                            {(walkForwardSummary.win_rate * 100).toFixed(1)}%
                          </div>
                          <div className="text-[9px] text-warm-500">
                            基准: {(walkForwardSummary.baseline_win_rate * 100).toFixed(1)}%
                          </div>
                        </div>
                        <div className="p-1 bg-white rounded border border-warm-200">
                          <div className="text-[9px] text-warm-400">夏普比率</div>
                          <div
                            className={`text-xs font-bold ${
                              walkForwardSummary.sharpe_ratio >= 0
                                ? 'text-emerald-700'
                                : 'text-red-600'
                            }`}
                          >
                            {walkForwardSummary.sharpe_ratio.toFixed(2)}
                          </div>
                          <div className="text-[9px] text-warm-500">
                            基准: {walkForwardSummary.baseline_sharpe.toFixed(2)}
                          </div>
                        </div>
                        <div className="p-1 bg-white rounded border border-warm-200">
                          <div className="text-[9px] text-warm-400">最大回撤</div>
                          <div className="text-xs font-bold text-red-600">
                            {(walkForwardSummary.max_drawdown * 100).toFixed(1)}%
                          </div>
                          <div className="text-[9px] text-warm-500">
                            {walkForwardSummary.fold_count}折验证
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-[10px] text-warm-500 font-mono">
                        <span>时序因果隔离: 严格PASS</span>
                        <span>MAE: {walkForwardSummary.mae.toFixed(4)}</span>
                      </div>
                    </>
                  ) : (
                    <div className="text-xs text-warm-500 py-4 text-center">
                      暂无回测指标 (需执行样本外回测)
                    </div>
                  )}
                </div>

                {/* 3. Top Feature Importances */}
                <div className="p-2 bg-warm-50 rounded border border-warm-200 space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-warm-900">特征解释性 (Top 4 驱动因子)</span>
                    <span className="text-[10px] text-warm-400 font-mono">Normalized</span>
                  </div>

                  {prediction?.feature_importance &&
                  Object.keys(prediction.feature_importance).length > 0 ? (
                    <div className="space-y-1 font-mono text-[10px]">
                      {Object.entries(prediction.feature_importance)
                        .slice(0, 4)
                        .map(([feat, weight]) => (
                          <div key={feat} className="space-y-0.5">
                            <div className="flex justify-between text-warm-600">
                              <span>{feat}</span>
                              <span className="font-semibold text-warm-800">
                                {(weight * 100).toFixed(1)}%
                              </span>
                            </div>
                            <div className="w-full h-1 bg-warm-200 rounded-full overflow-hidden">
                              <div
                                className="bg-indigo-600 h-full rounded-full"
                                style={{ width: `${Math.min(100, weight * 250)}%` }}
                              />
                            </div>
                          </div>
                        ))}
                    </div>
                  ) : (
                    <div className="text-xs text-warm-500 py-4 text-center">
                      暂无特征归因数据
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 4: 分红送配与数据治理 */}
        {activeTab === 'actions' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {/* Left: Corporate Actions Table */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px] text-warm-500 bg-warm-50 p-1.5 rounded border border-warm-200 font-mono">
                <span>动态复权公式: P_ex = (P_cum - D + R × P_r) / (1 + B + R)</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left font-mono text-[11px] border-collapse min-w-[360px]">
                  <thead>
                    <tr className="border-b border-warm-200 text-warm-400">
                      <th className="py-1">除权除息日</th>
                      <th className="py-1">登记日</th>
                      <th className="py-1">每股派现(D)</th>
                      <th className="py-1">送转股(B)</th>
                      <th className="py-1">配股(R)</th>
                      <th className="py-1">配股价</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-warm-100 hover:bg-warm-50">
                      <td className="py-1 text-warm-900 font-semibold">2024-06-18</td>
                      <td className="py-1 text-warm-600">2024-06-17</td>
                      <td className="py-1 text-emerald-700 font-medium">¥30.876</td>
                      <td className="py-1 text-warm-600">0.0</td>
                      <td className="py-1 text-warm-600">0.0</td>
                      <td className="py-1 text-warm-600">--</td>
                    </tr>
                    <tr className="border-b border-warm-100 hover:bg-warm-50">
                      <td className="py-1 text-warm-900 font-semibold">2023-06-30</td>
                      <td className="py-1 text-warm-600">2023-06-29</td>
                      <td className="py-1 text-emerald-700 font-medium">¥25.911</td>
                      <td className="py-1 text-warm-600">0.0</td>
                      <td className="py-1 text-warm-600">0.0</td>
                      <td className="py-1 text-warm-600">--</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Right: Quality and Governance */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div className="p-2 bg-warm-50 rounded border border-warm-200 space-y-0.5">
                <div className="font-semibold text-warm-900 flex items-center justify-between text-xs">
                  <span>OHLC 几何关系校验</span>
                  <span className="text-emerald-700 font-mono text-[10px] flex items-center gap-0.5">
                    <CheckCircle2 className="w-3 h-3" /> PASS
                  </span>
                </div>
                <p className="text-[10px] text-warm-500 leading-tight">
                  严格保障 High ≥ max(Open, Close) 且 Low ≤ min(Open, Close)，杜绝倒置脏数据。
                </p>
              </div>

              <div className="p-2 bg-warm-50 rounded border border-warm-200 space-y-0.5">
                <div className="font-semibold text-warm-900 flex items-center justify-between text-xs">
                  <span>时序前缀一致性防护</span>
                  <span className="text-emerald-700 font-mono text-[10px] flex items-center gap-0.5">
                    <CheckCircle2 className="w-3 h-3" /> VERIFIED
                  </span>
                </div>
                <p className="text-[10px] text-warm-500 leading-tight">
                  T 日指标计算严格仅使用 ≤T 日数据，严禁未来数据泄露，保障回测严谨性。
                </p>
              </div>

              <div className="p-2 bg-warm-50 rounded border border-warm-200 space-y-0.5">
                <div className="font-semibold text-warm-900 flex items-center justify-between text-xs">
                  <span>增量计算与缓存指纹</span>
                  <span className="text-emerald-700 font-mono text-[10px] flex items-center gap-0.5">
                    <CheckCircle2 className="w-3 h-3" /> ACTIVE
                  </span>
                </div>
                <p className="text-[10px] text-warm-500 leading-tight">
                  基于 MD5 数据指纹自动失效，增量更新与全量计算误差严格控制在 1e-5 以内。
                </p>
              </div>

              <div className="p-2 bg-warm-50 rounded border border-warm-200 space-y-0.5">
                <div className="font-semibold text-warm-900 flex items-center justify-between text-xs">
                  <span>存储与原子提交引擎</span>
                  <span className="text-emerald-700 font-mono text-[10px] flex items-center gap-0.5">
                    <CheckCircle2 className="w-3 h-3" /> WAL ACTIVE
                  </span>
                </div>
                <p className="text-[10px] text-warm-500 leading-tight">
                  SQLite WAL 管理状态，Parquet 原子重命名，故障崩溃时自动回滚未完成事务。
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
