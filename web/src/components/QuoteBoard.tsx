import React from 'react';
import {
  ShieldCheck,
  Database,
  Zap,
  Download,
  Activity,
  RefreshCw,
  TriangleAlert,
} from 'lucide-react';
import type { ColorScheme, QuoteResponse, Security } from '../types';
import { fmtAmount, fmtDate, fmtPrice, fmtPct, fmtSigned, fmtVolume, tone } from '../lib/format';

interface QuoteBoardProps {
  security?: Security;
  quote: QuoteResponse | null;
  colorScheme: ColorScheme;
  isCached: boolean;
  qualityStatus: string;
  dataOrigin: string;
  sourceInterface: string;
  isLoading: boolean;
  activeTaskCount: number;
  onOpenUpdate: () => void;
  onOpenMonitor: () => void;
  onRefresh: () => void;
}

const ORIGIN_LABEL: Record<string, { text: string; cls: string }> = {
  real_provider: { text: '真实行情', cls: 'chip--ok' },
  manual_import: { text: '手工导入', cls: 'chip--warn' },
  synthetic_test: { text: '合成测试', cls: 'chip--danger' },
  unknown: { text: '来源未知', cls: 'chip--warn' },
};

export const QuoteBoard: React.FC<QuoteBoardProps> = ({
  security,
  quote,
  colorScheme,
  isCached,
  qualityStatus,
  dataOrigin,
  sourceInterface,
  isLoading,
  activeTaskCount,
  onOpenUpdate,
  onOpenMonitor,
  onRefresh,
}) => {
  const symbol = security?.symbol ?? quote?.symbol ?? '—';
  const name = security?.name ?? '标的资产';

  const price = quote?.last_price ?? null;
  const change = quote?.change ?? null;
  const pct = quote?.pct_change ?? null;
  const prevClose = quote?.prev_close ?? null;

  const upIsRed = colorScheme === 'CN';
  const direction = tone(change);
  const priceTone =
    direction === 'flat' ? 'flat' : direction === 'up' ? (upIsRed ? 'up' : 'down') : upIsRed ? 'down' : 'up';
  const deltaTone = priceTone === 'flat' ? 'flat' : priceTone;

  const origin = ORIGIN_LABEL[dataOrigin] ?? ORIGIN_LABEL.unknown;
  const clsFor = (value: number | null | undefined) => {
    const t = tone(value);
    if (t === 'flat') return 'flat';
    return (t === 'up') === upIsRed ? 'up' : 'down';
  };
  const metrics: Array<{ label: string; value: string; cls?: string; hidden?: boolean }> = [
    { label: '今开', value: fmtPrice(quote?.open) },
    {
      label: '最高',
      value: fmtPrice(quote?.high),
      cls: prevClose !== null ? clsFor((quote?.high ?? 0) - prevClose) : undefined,
    },
    {
      label: '最低',
      value: fmtPrice(quote?.low),
      cls: prevClose !== null ? clsFor((quote?.low ?? 0) - prevClose) : undefined,
    },
    { label: '昨收', value: fmtPrice(prevClose) },
    { label: '成交量', value: fmtVolume(quote?.volume), hidden: true },
    { label: '成交额', value: fmtAmount(quote?.amount), hidden: true },
  ];

  return (
    <section className="quote-board" aria-label="行情看板">
      <div className="shell-bleed quote-board__inner">
        <div className="identity">
          <div className="identity__line">
            <span className="identity__symbol">{symbol}</span>
            <h1 className="identity__name">{name}</h1>
            {security?.market === 'CN_HK' ? (
              <span className="chip chip--warn" title="港股数据链路尚未通过生产级完整性验证">
                <TriangleAlert size={10} />
                HK · 未验证
              </span>
            ) : (
              <span className="chip chip--quiet">{security?.market ?? 'CN_A'}</span>
            )}
          </div>
          <div className="identity__meta">
            <span>{security?.currency ?? 'CNY'}</span>
            <span>·</span>
            <span>{security?.asset_type ?? 'stock'}</span>
            <span>·</span>
            <span>{security?.listing_status ?? 'listed'}</span>
            {security?.listed_date && (
              <>
                <span>·</span>
                <span>L {fmtDate(security.listed_date)}</span>
              </>
            )}
          </div>
        </div>

        <div className="price-block">
          <span className={'price ' + priceTone}>
            {price === null ? '—' : fmtPrice(price)}
          </span>
          {price !== null && (
            <span className={'delta delta--' + deltaTone}>
              <span>{fmtSigned(change)}</span>
              <span>{fmtPct(pct)}</span>
            </span>
          )}
          <span className="price__stamp">{quote ? fmtDate(quote.ts) + ' 收盘' : '暂无快照'}</span>
        </div>

        <dl className="quote-metrics">
          {metrics.map((m) => (
            <div className={'metric ' + (m.hidden ? 'hidden xl:flex' : '')} key={m.label}>
              <dt className="metric__label">{m.label}</dt>
              <dd className={'metric__value ' + (m.cls ?? '')}>{m.value}</dd>
            </div>
          ))}
        </dl>

        <div className="quote-side">
          {qualityStatus === 'PASS' ? (
            <span className="chip chip--ok hidden 2xl:inline-flex" title="QualityValidator 已校验">
              <ShieldCheck size={10} />
              质检 PASS
            </span>
          ) : (
            <span className="chip chip--warn" title="数据质量状态">
              <ShieldCheck size={10} />
              {qualityStatus}
            </span>
          )}

          <span
            className={'chip ' + (isCached ? 'chip--warn' : 'chip--quiet') + ' hidden 2xl:inline-flex'}
            title={isCached ? 'LRU 内存缓存命中' : '直接读取复合存储引擎'}
          >
            <Zap size={10} />
            {isCached ? 'LRU 命中' : '本地存储'}
          </span>

          <span
            className={'chip ' + origin.cls + ' hidden 2xl:inline-flex'}
            title={'数据接口: ' + (sourceInterface || 'local_store')}
          >
            <Database size={10} />
            {origin.text}
          </span>

          <button type="button" className="btn btn--primary" onClick={onOpenUpdate}>
            <Download size={12} />
            更新行情
          </button>

          <button
            type="button"
            className="btn btn--ghost relative"
            onClick={onOpenMonitor}
            title="行情采集与更新任务监视器"
          >
            <Activity size={12} />
            <span className="hidden xl:inline">任务监控</span>
            {activeTaskCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-market-green" />
            )}
          </button>

          <button
            type="button"
            className="btn btn--icon"
            onClick={onRefresh}
            disabled={isLoading}
            title="刷新行情与指标"
            aria-label="刷新行情与指标"
          >
            <RefreshCw size={12} className={isLoading ? 'spin' : undefined} />
          </button>
        </div>
      </div>
    </section>
  );
};
