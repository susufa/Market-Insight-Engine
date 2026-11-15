import React from 'react';
import { ShieldCheck, Database, Zap, RefreshCw, CloudDownload, Activity } from 'lucide-react';
import { QuoteResponse, Security, ColorScheme } from '../types';

interface StockHeaderProps {
  security?: Security;
  quote?: QuoteResponse | null;
  colorScheme: ColorScheme;
  isCached: boolean;
  qualityStatus: string;
  sourceId: string;
  dataOrigin?: string;
  sourceInterface?: string;
  onRefresh: () => void;
  isLoading: boolean;
  onOpenUpdateModal?: () => void;
  onOpenTaskMonitor?: () => void;
  activeTaskCount?: number;
}

export const StockHeader: React.FC<StockHeaderProps> = ({
  security,
  quote,
  colorScheme,
  isCached,
  qualityStatus,
  sourceId,
  dataOrigin,
  sourceInterface,
  onRefresh,
  isLoading,
  onOpenUpdateModal,
  onOpenTaskMonitor,
  activeTaskCount = 0,
}) => {
  const symbol = security?.symbol || quote?.symbol || '--';
  const name = security?.name || '标的资产';
  const price = quote?.last_price ?? 0;
  const change = quote?.change ?? 0;
  const pctChange = quote?.pct_change ?? 0;
  const high = quote?.high ?? 0;
  const low = quote?.low ?? 0;
  const open = quote?.open ?? 0;
  const prevClose = quote?.prev_close ?? 0;
  const volume = quote?.volume ?? 0;
  const amount = quote?.amount ?? 0;

  const getChangeColor = (val: number) => {
    if (val === 0) return 'text-warm-500';
    const isPositive = val > 0;
    if (colorScheme === 'CN') {
      return isPositive ? 'text-market-red' : 'text-market-green';
    } else {
      return isPositive ? 'text-market-green' : 'text-market-red';
    }
  };

  const getBgColor = (val: number) => {
    if (val === 0) return 'bg-warm-100 text-warm-700';
    const isPositive = val > 0;
    if (colorScheme === 'CN') {
      return isPositive
        ? 'bg-red-50 text-market-red border-red-200'
        : 'bg-green-50 text-market-green border-green-200';
    } else {
      return isPositive
        ? 'bg-green-50 text-market-green border-green-200'
        : 'bg-red-50 text-market-red border-red-200';
    }
  };

  const formatNumber = (num: number, decimals = 2) => {
    return num.toLocaleString('zh-CN', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  };

  const formatVolume = (v: number) => {
    if (v >= 100000000) return (v / 100000000).toFixed(2) + ' 亿股';
    if (v >= 10000) return (v / 10000).toFixed(2) + ' 万股';
    return v.toLocaleString() + ' 股';
  };

  const formatAmount = (a: number) => {
    if (a >= 100000000) return (a / 100000000).toFixed(2) + ' 亿元';
    if (a >= 10000) return (a / 10000).toFixed(2) + ' 万元';
    return a.toLocaleString() + ' 元';
  };

  return (
    <div className="bg-white border-b border-warm-200 px-3 sm:px-4 lg:px-6 py-2">
      <div className="w-full max-w-[2560px] 2xl:max-w-[3400px] mx-auto flex flex-wrap items-center justify-between gap-y-2 gap-x-4">
        {/* Left: Code, Name, Main Price */}
        <div className="flex items-center gap-3 sm:gap-4 shrink-0">
          <div>
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="text-base sm:text-lg font-bold font-mono text-warm-900 tracking-tight">
                {symbol}
              </span>
              <span className="text-sm sm:text-base font-semibold text-warm-800">
                {name}
              </span>
              {security?.market === 'CN_HK' ? (
                <span className="text-[10px] font-mono px-1.5 py-0.5 bg-amber-50 text-amber-800 rounded border border-amber-300 font-semibold" title="港股真实数据链路处于实验阶段，尚未通过生产级完整性验证 (NOT VERIFIED)">
                  港股 (NOT VERIFIED)
                </span>
              ) : (
                <span className="text-[10px] font-mono px-1.5 py-0.5 bg-warm-100 text-warm-600 rounded border border-warm-200">
                  {security?.market ?? 'CN_A'}
                </span>
              )}
            </div>
            <div className="text-[10px] sm:text-[11px] text-warm-400 font-mono">
              币种: {security?.currency ?? 'CNY'} | 状态: {security?.listing_status ?? 'listed'}
            </div>
          </div>

          {/* Big Price & Change */}
          <div className="flex items-baseline gap-2 sm:gap-3 pl-2 sm:pl-3 border-l border-warm-200">
            <span className={`text-xl sm:text-2xl font-bold font-mono tracking-tight ${getChangeColor(change)}`}>
              {price > 0 ? formatNumber(price) : '--'}
            </span>
            <div className={`flex items-center gap-1 sm:gap-1.5 text-xs font-mono font-semibold px-1.5 sm:px-2 py-0.5 rounded border ${getBgColor(change)}`}>
              <span>{change > 0 ? '+' : ''}{formatNumber(change)}</span>
              <span>({pctChange > 0 ? '+' : ''}{pctChange.toFixed(2)}%)</span>
            </div>
          </div>
        </div>

        {/* Center: Market Bar Key Metrics */}
        <div className="flex flex-wrap items-center gap-3 sm:gap-4 text-xs font-mono">
          <div className="flex flex-col">
            <span className="text-[10px] text-warm-400 font-sans">今开</span>
            <span className="text-warm-700 font-medium">{open > 0 ? formatNumber(open) : '--'}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] text-warm-400 font-sans">最高</span>
            <span className={`font-medium ${getChangeColor(high - prevClose)}`}>
              {high > 0 ? formatNumber(high) : '--'}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] text-warm-400 font-sans">最低</span>
            <span className={`font-medium ${getChangeColor(low - prevClose)}`}>
              {low > 0 ? formatNumber(low) : '--'}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] text-warm-400 font-sans">昨收</span>
            <span className="text-warm-700 font-medium">{prevClose > 0 ? formatNumber(prevClose) : '--'}</span>
          </div>
          <div className="hidden sm:flex flex-col border-l border-warm-200 pl-3">
            <span className="text-[10px] text-warm-400 font-sans">成交量</span>
            <span className="text-warm-800 font-medium">{volume > 0 ? formatVolume(volume) : '--'}</span>
          </div>
          <div className="hidden sm:flex flex-col">
            <span className="text-[10px] text-warm-400 font-sans">成交额</span>
            <span className="text-warm-800 font-medium">{amount > 0 ? formatAmount(amount) : '--'}</span>
          </div>
        </div>

        {/* Right: Data Quality & Provenance Badges */}
        <div className="flex items-center gap-2 text-[11px] font-mono shrink-0">
          {qualityStatus === 'PASS' ? (
            <div className="flex items-center gap-1 px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded border border-emerald-200" title="数据质量已由 QualityValidator 校验">
              <ShieldCheck className="w-3 h-3 text-emerald-600" />
              <span>质检: PASS</span>
            </div>
          ) : (
            <div className="flex items-center gap-1 px-2 py-0.5 bg-amber-50 text-amber-800 rounded border border-amber-300" title={`数据状态: ${qualityStatus}`}>
              <ShieldCheck className="w-3 h-3 text-amber-600" />
              <span>状态: {qualityStatus}</span>
            </div>
          )}

          <div className={`flex items-center gap-1 px-2 py-0.5 rounded border ${
            isCached ? 'bg-amber-50 text-amber-800 border-amber-200' : 'bg-warm-100 text-warm-700 border-warm-200'
          }`} title={isCached ? "LRU 内存缓存命中 (<5ms)" : "直接读取存储引擎"}>
            <Zap className={`w-3 h-3 ${isCached ? 'text-amber-600' : 'text-warm-500'}`} />
            <span>{isCached ? 'LRU 命中' : '本地存储'}</span>
          </div>

          <div className="hidden 2xl:flex items-center gap-1 px-2 py-0.5 bg-warm-100 text-warm-600 rounded border border-warm-200" title={`数据接口: ${sourceInterface || sourceId} (${dataOrigin || 'real_provider'})`}>
            <Database className="w-3 h-3 text-warm-500" />
            <span className="max-w-[200px] truncate">{sourceInterface || sourceId}</span>
          </div>

          {onOpenUpdateModal && (
            <button
              onClick={onOpenUpdateModal}
              className="px-2 py-1 rounded bg-warm-800 hover:bg-warm-900 text-white font-sans text-xs font-medium shadow-xs flex items-center gap-1.5 transition-colors"
              title="主动获取与更新行情数据"
            >
              <CloudDownload className="w-3.5 h-3.5" />
              <span>更新行情</span>
            </button>
          )}

          {onOpenTaskMonitor && (
            <button
              onClick={onOpenTaskMonitor}
              className="px-2 py-1 rounded bg-white hover:bg-warm-100 text-warm-700 border border-warm-300 font-sans text-xs font-medium shadow-xs flex items-center gap-1.5 transition-colors relative"
              title="查看行情采集与更新任务状态"
            >
              <Activity className="w-3.5 h-3.5 text-warm-600" />
              <span>任务监控</span>
              {activeTaskCount > 0 && (
                <span className="w-2 h-2 rounded-full bg-blue-500 animate-ping absolute -top-0.5 -right-0.5" />
              )}
            </button>
          )}

          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="p-1 rounded hover:bg-warm-100 text-warm-500 hover:text-warm-800 border border-warm-200 transition-colors"
            title="刷新行情与K线"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
    </div>
  );
};
