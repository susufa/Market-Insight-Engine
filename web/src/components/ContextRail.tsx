import React, { useMemo } from 'react';
import { Sparkles } from 'lucide-react';
import type {
  ColorScheme,
  IndicatorRow,
  PredictionResult,
  QuoteResponse,
  Security,
} from '../types';
import { clamp, fmtDate, fmtPct, fmtPrice, fmtShare, pctFromRatio, tone } from '../lib/format';

interface ContextRailProps {
  quote: QuoteResponse | null;
  security?: Security;
  bars: IndicatorRow[];
  latestIndicator: IndicatorRow | null;
  prediction: PredictionResult | null;
  colorScheme: ColorScheme;
  qualityStatus: string;
  isCached: boolean;
  dataOrigin: string;
  sourceInterface: string;
}

const MA_STROKE: Record<string, string> = {
  MA5: '#2D6C8E',
  MA10: '#B4552E',
  MA20: '#9A7B2F',
  MA60: '#7A7480',
};

export const ContextRail: React.FC<ContextRailProps> = ({
  quote,
  security,
  bars,
  latestIndicator,
  prediction,
  colorScheme,
  qualityStatus,
  isCached,
  dataOrigin,
  sourceInterface,
}) => {
  const upIsRed = colorScheme === 'CN';
  const toneClass = (value: number | null | undefined) => {
    const t = tone(value);
    if (t === 'flat') return 'flat';
    return (t === 'up') === upIsRed ? 'up' : 'down';
  };

  const price = quote?.last_price ?? null;
  const low = quote?.low ?? null;
  const high = quote?.high ?? null;
  const prevClose = quote?.prev_close ?? null;
  const position =
    price !== null && low !== null && high !== null && high > low
      ? clamp(((price - low) / (high - low)) * 100, 0, 100)
      : null;

  const amplitude =
    high !== null && low !== null && prevClose !== null && prevClose > 0
      ? ((high - low) / prevClose) * 100
      : null;
  const vwap =
    quote && quote.volume > 0 && quote.amount > 0 ? quote.amount / quote.volume : null;

  const maRows = latestIndicator
    ? [
        { label: 'MA5', value: latestIndicator.ma_5 },
        { label: 'MA10', value: latestIndicator.ma_10 },
        { label: 'MA20', value: latestIndicator.ma_20 },
        { label: 'MA60', value: latestIndicator.ma_60 },
      ]
    : [];

  const dev = (ma: number | null | undefined) =>
    ma && price ? ((price - ma) / ma) * 100 : null;

  /* ---- 60-session trend block (computed from local bars only) -------- */
  const trend = useMemo(() => {
    const closes = bars.slice(-60).map((b) => b.close);
    if (closes.length < 2) return null;
    const first = closes[0];
    const last = closes[closes.length - 1];
    const hi = Math.max(...closes);
    const lo = Math.min(...closes);
    const span = hi - lo || 1;
    const points = closes
      .map((c, i) => {
        const x = (i / (closes.length - 1)) * 100;
        const y = 4 + (1 - (c - lo) / span) * 32;
        return x.toFixed(2) + ',' + y.toFixed(2);
      })
      .join(' ');
    const rets: number[] = [];
    for (let i = 1; i < closes.length; i++) {
      if (closes[i - 1] > 0) rets.push((closes[i] - closes[i - 1]) / closes[i - 1]);
    }
    const mean = rets.reduce((a, b) => a + b, 0) / Math.max(1, rets.length);
    const variance =
      rets.reduce((a, b) => a + (b - mean) * (b - mean), 0) / Math.max(1, rets.length - 1);
    const vol = Math.sqrt(Math.max(0, variance)) * Math.sqrt(252) * 100;
    return {
      change: ((last - first) / (first || 1)) * 100,
      hi,
      lo,
      vol,
      points,
      color:
        (last >= first) === upIsRed
          ? '#DC2626'
          : '#16A34A',
      count: closes.length,
    };
  }, [bars, upIsRed]);

  return (
    <aside className="rail" aria-label="指标侧栏">
      <div className="rail-panel">
        <section className="rail-section">
          <div className="rail-card__head">
            <span className="eyebrow">SESSION · 日内区间</span>
            <span className="eyebrow" style={{ color: '#B4AFA7' }}>
              {fmtDate(quote?.ts)}
            </span>
          </div>

          <div className="flex flex-col gap-1">
            <div className="range-track">
              <div className="range-fill" style={{ width: (position ?? 0) + '%' }} />
              {position !== null && <div className="range-marker" style={{ left: position + '%' }} />}
            </div>
            <div className="range-labels">
              <span>低 {fmtPrice(low)}</span>
              <span>高 {fmtPrice(high)}</span>
            </div>
          </div>

          <div className="mini-grid">
            <div className="mini-stat">
              <span className="eyebrow">振幅</span>
              <span className="mini-stat__v">
                {amplitude === null ? '—' : amplitude.toFixed(2) + '%'}
              </span>
            </div>
            <div className="mini-stat">
              <span className="eyebrow">VWAP</span>
              <span className="mini-stat__v">{fmtPrice(vwap)}</span>
            </div>
            <div className="mini-stat">
              <span className="eyebrow">RSI(14)</span>
              <span className="mini-stat__v">{fmtPrice(latestIndicator?.rsi_14, 1)}</span>
            </div>
            <div className="mini-stat">
              <span className="eyebrow">ATR(14)</span>
              <span className="mini-stat__v">{fmtPrice(latestIndicator?.atr_14)}</span>
            </div>
          </div>
        </section>

        <section className="rail-section">
          <div className="rail-card__head">
            <span className="eyebrow">MA · 均线系统</span>
            <span className="eyebrow" style={{ color: '#B4AFA7' }}>
              相对现价
            </span>
          </div>
          {maRows.length === 0 ? (
            <div className="panel-empty">
              <span className="text-[0.72rem] font-medium text-warm-600">暂无指标</span>
              <span className="text-[0.65rem] text-warm-400">需要至少 60 根有效日线</span>
            </div>
          ) : (
            <div className="ledger">
              {maRows.map((row) => {
                const d = dev(row.value);
                return (
                  <div className="ledger-row" key={row.label}>
                    <span className="ledger-row__k">
                      <span
                        className="legend-swatch"
                        style={{ background: MA_STROKE[row.label] }}
                      />
                      {row.label}
                    </span>
                    <span className="flex items-baseline gap-2">
                      <span className="ledger-row__v">{fmtPrice(row.value)}</span>
                      <span className={'num text-[0.64rem] ' + toneClass(d)}>{fmtPct(d)}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="rail-section">
          <div className="rail-card__head">
            <span className="eyebrow">FORECAST · 前向信号</span>
            <span className="chip chip--quiet">{prediction ? prediction.horizon + 'D' : 'N/A'}</span>
          </div>

          {!prediction ? (
            <div className="panel-empty">
              <span className="flex items-center gap-1 text-[0.72rem] font-medium text-warm-600">
                <Sparkles size={11} className="text-warm-400" />
                暂无预测输出
              </span>
              <span className="text-[0.65rem] text-warm-400">
                预测约需 ≥95 根日线、样本外回测 ≥320 根 · 不以假数据兜底
              </span>
            </div>
          ) : (
            <>
              <div className="flex items-baseline gap-2">
                <span
                  className={'num text-[1.15rem] font-semibold ' + toneClass(prediction.point_estimate)}
                >
                  {pctFromRatio(prediction.point_estimate)}
                </span>
                <span className="num text-[0.62rem] text-warm-400">
                  [{pctFromRatio(prediction.lower_bound)}, {pctFromRatio(prediction.upper_bound)}]
                </span>
              </div>

              <div className="flex flex-col gap-1">
                <div className="ratio-bar" style={{ height: '0.28rem' }}>
                  <div
                    className="ratio-bar__up"
                    style={{ width: (prediction.probabilities?.up ?? 0.33) * 100 + '%' }}
                  />
                  <div
                    className="ratio-bar__flat"
                    style={{ width: (prediction.probabilities?.flat ?? 0.34) * 100 + '%' }}
                  />
                  <div
                    className="ratio-bar__down"
                    style={{ width: (prediction.probabilities?.down ?? 0.33) * 100 + '%' }}
                  />
                </div>
                <div className="flex justify-between text-[0.6rem] num">
                  <span style={{ color: upIsRed ? '#DC2626' : '#16A34A' }}>
                    涨 {fmtShare(prediction.probabilities?.up)}
                  </span>
                  <span className="text-warm-500">平 {fmtShare(prediction.probabilities?.flat)}</span>
                  <span style={{ color: upIsRed ? '#16A34A' : '#DC2626' }}>
                    跌 {fmtShare(prediction.probabilities?.down)}
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between text-[0.6rem] text-warm-400">
                <span className="num truncate" title={prediction.model_name}>
                  {prediction.model_name}
                </span>
                <span className="num">{fmtDate(prediction.as_of)}</span>
              </div>
            </>
          )}
        </section>

        <section className="rail-section rail-section--grow">
          <div className="rail-card__head">
            <span className="eyebrow">TREND · 近 {trend?.count ?? 60} 日</span>
            <span className={'num text-[0.66rem] ' + toneClass(trend?.change)}>
              {fmtPct(trend?.change)}
            </span>
          </div>

          {!trend ? (
            <div className="panel-empty">
              <span className="text-[0.7rem] text-warm-400">暂无足够历史用于绘制区间走势</span>
            </div>
          ) : (
            <>
              <div className="spark-wrap">
                <svg
                  className="spark-svg"
                  viewBox="0 0 100 40"
                  preserveAspectRatio="none"
                  role="img"
                  aria-label={'近 ' + trend.count + ' 个交易日收盘走势'}
                >
                  <polygon
                    points={trend.points + ' 100,40 0,40'}
                    fill={trend.color}
                    opacity={0.08}
                  />
                  <polyline
                    points={trend.points}
                    fill="none"
                    stroke={trend.color}
                    strokeWidth={1}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              </div>
              <div className="mini-grid">
                <div className="mini-stat">
                  <span className="eyebrow">区间高</span>
                  <span className="mini-stat__v">{fmtPrice(trend.hi)}</span>
                </div>
                <div className="mini-stat">
                  <span className="eyebrow">区间低</span>
                  <span className="mini-stat__v">{fmtPrice(trend.lo)}</span>
                </div>
                <div className="mini-stat">
                  <span className="eyebrow">年化波动</span>
                  <span className="mini-stat__v">{trend.vol.toFixed(1)}%</span>
                </div>
                <div className="mini-stat">
                  <span className="eyebrow">样本</span>
                  <span className="mini-stat__v">{trend.count} 日</span>
                </div>
              </div>
            </>
          )}
        </section>

        <div className="rail-footer">
          <span className="flex items-center justify-between">
            <span className="eyebrow">LINEAGE</span>
            <span className={'chip ' + (qualityStatus === 'PASS' ? 'chip--ok' : 'chip--warn')}>
              {qualityStatus}
            </span>
          </span>
          <span className="num text-[0.6rem] text-warm-500 truncate" title={sourceInterface}>
            {dataOrigin || 'unknown'} · {sourceInterface || 'local_store'}
          </span>
          <span className="num text-[0.6rem] text-warm-400">
            {security?.symbol ?? '—'} · {security?.market ?? 'CN_A'} · {isCached ? 'LRU 命中' : '存储读取'}
          </span>
        </div>
      </div>
    </aside>
  );
};
