import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { StockHeader } from './components/StockHeader';
import { StockChart } from './components/StockChart';
import { SecondaryTabs } from './components/SecondaryTabs';
import { DataUpdateModal } from './components/DataUpdateModal';
import { TaskMonitorDrawer } from './components/TaskMonitorDrawer';
import {
  ColorScheme,
  IndexTicker,
  QuoteResponse,
  Security,
  Timeframe,
  AdjustType,
  IndicatorRow,
  BreadthReport,
  SectorSummary,
  RelativePerformance,
  PredictionResult,
  ModelEvaluationSummary,
} from './types';
import {
  fetchBars,
  fetchQuote,
  fetchSecurities,
  fetchIndicators,
  fetchMarketBreadth,
  fetchSectors,
  fetchRelativePerformance,
  fetchForecast,
  fetchWalkForwardReport,
} from './api';

// Static benchmark reference indices (labeled clearly as reference to avoid misleading real-time representation)
const DEFAULT_INDICES: IndexTicker[] = [
  { symbol: '000001.SH', name: '上证指数(基准)', price: 3088.24, change: 16.42, pct_change: 0.54 },
  { symbol: '399001.SZ', name: '深证成指(基准)', price: 9872.15, change: 82.30, pct_change: 0.84 },
  { symbol: '399006.SZ', name: '创业板指(基准)', price: 1945.80, change: 21.15, pct_change: 1.10 },
  { symbol: 'HSI.HK', name: '恒生指数(基准)', price: 17855.20, change: -45.10, pct_change: -0.25 },
];

export const App: React.FC = () => {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('600519.SH');
  const [timeframe, setTimeframe] = useState<Timeframe>('1d');
  const [adjType, setAdjType] = useState<AdjustType>('none');
  const [colorScheme, setColorScheme] = useState<ColorScheme>('CN');

  const [securities, setSecurities] = useState<Security[]>([]);
  const [quote, setQuote] = useState<QuoteResponse | null>(null);
  const [indicatorBars, setIndicatorBars] = useState<IndicatorRow[]>([]);
  const [breadth, setBreadth] = useState<BreadthReport | null>(null);
  const [sectors, setSectors] = useState<SectorSummary[]>([]);
  const [relativePerf, setRelativePerf] = useState<RelativePerformance | null>(null);
  const [prediction, setPrediction] = useState<PredictionResult | null>(null);
  const [walkForwardSummary, setWalkForwardSummary] = useState<ModelEvaluationSummary | null>(null);

  const [isCached, setIsCached] = useState<boolean>(false);
  const [qualityStatus, setQualityStatus] = useState<string>('PASS');
  const [sourceId, setSourceId] = useState<string>('local_store');
  const [dataOrigin, setDataOrigin] = useState<string>('real_provider');
  const [sourceInterface, setSourceInterface] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const [isUpdateModalOpen, setIsUpdateModalOpen] = useState<boolean>(false);
  const [isTaskMonitorOpen, setIsTaskMonitorOpen] = useState<boolean>(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);

  // Load securities list once on mount
  useEffect(() => {
    fetchSecurities().then((res) => {
      if (res && res.items) {
        setSecurities(res.items);
      }
    });
  }, []);

  // Load macro statistics (breadth & sectors) once on mount
  useEffect(() => {
    fetchMarketBreadth('CN_A').then((b) => setBreadth(b)).catch(() => {});
    fetchSectors('000001.SH').then((s) => setSectors(s)).catch(() => {});
  }, []);

  // Load quote, indicator-enriched bars, and relative performance
  const loadMarketData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [quoteRes, indRes, perfRes, predRes, wfRes] = await Promise.all([
        fetchQuote(selectedSymbol),
        fetchIndicators(selectedSymbol, timeframe, adjType),
        fetchRelativePerformance(selectedSymbol, '000001.SH'),
        fetchForecast(selectedSymbol),
        fetchWalkForwardReport(selectedSymbol),
      ]);

      setQuote(quoteRes);
      if (quoteRes?.data_origin) {
        setDataOrigin(quoteRes.data_origin);
      }
      if (quoteRes?.source_interface) {
        setSourceInterface(quoteRes.source_interface);
      }

      if (indRes && indRes.rows && indRes.rows.length > 0) {
        setIndicatorBars(indRes.rows);
        setIsCached(indRes.is_cached);
        setQualityStatus('PASS');
        setSourceId('analysis_engine');
      } else {
        // Fallback to fetchBars if indicators endpoint returns empty
        const barsRes = await fetchBars(selectedSymbol, timeframe, adjType);
        if (barsRes && barsRes.bars && barsRes.bars.length > 0) {
          setIndicatorBars(barsRes.bars);
          setIsCached(barsRes.is_cached);
          setQualityStatus(barsRes.data_quality_status || 'PASS');
          setSourceId(barsRes.source_id || 'local_store');
          if (barsRes.data_origin) setDataOrigin(barsRes.data_origin);
          if (barsRes.source_interface) setSourceInterface(barsRes.source_interface);
        } else {
          setIndicatorBars([]);
          setIsCached(false);
          setQualityStatus(barsRes.data_quality_status || 'NO_DATA');
          setSourceId(barsRes.source_id || 'local_store');
          setDataOrigin(barsRes.data_origin || 'unknown');
          setSourceInterface(barsRes.source_interface || '');
        }
      }
      setRelativePerf(perfRes);
      setPrediction(predRes);
      setWalkForwardSummary(wfRes);
    } catch (err) {
      console.error('Failed to load market data:', err);
    } finally {
      setIsLoading(false);
    }
  }, [selectedSymbol, timeframe, adjType]);

  useEffect(() => {
    loadMarketData();
  }, [loadMarketData]);

  const currentSecurity = securities.find((s) => s.symbol === selectedSymbol);
  const latestIndicator = indicatorBars.length > 0 ? indicatorBars[indicatorBars.length - 1] : null;

  return (
    <div className="min-h-screen bg-warm-50 flex flex-col font-sans text-warm-800">
      {/* 1. Global Navigation Bar */}
      <Header
        indices={DEFAULT_INDICES}
        securities={securities}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={setSelectedSymbol}
        colorScheme={colorScheme}
      />

      {/* 2. Security Summary & Quote Bar */}
      <StockHeader
        security={currentSecurity}
        quote={quote}
        colorScheme={colorScheme}
        isCached={isCached}
        qualityStatus={qualityStatus}
        sourceId={sourceId}
        dataOrigin={dataOrigin}
        sourceInterface={sourceInterface}
        onRefresh={loadMarketData}
        isLoading={isLoading}
        onOpenUpdateModal={() => setIsUpdateModalOpen(true)}
        onOpenTaskMonitor={() => setIsTaskMonitorOpen(true)}
        activeTaskCount={activeTaskId ? 1 : 0}
      />

      {/* 3. Main Chart & Toolbars (Adaptive width up to 4K, height bounded within viewports) */}
      <main className="flex-1 w-full max-w-[2560px] 2xl:max-w-[3400px] mx-auto px-2 sm:px-4 lg:px-6 py-2">
        <StockChart
          bars={indicatorBars}
          timeframe={timeframe}
          adjType={adjType}
          colorScheme={colorScheme}
          onTimeframeChange={setTimeframe}
          onAdjTypeChange={setAdjType}
          onColorSchemeChange={setColorScheme}
          isLoading={isLoading}
        />

        {/* 4. Secondary Information & Governance Tabs */}
        <div className="mt-2">
          <SecondaryTabs
            quote={quote}
            security={currentSecurity}
            breadth={breadth}
            sectors={sectors}
            relativePerformance={relativePerf}
            latestIndicator={latestIndicator}
            prediction={prediction}
            walkForwardSummary={walkForwardSummary}
          />
        </div>
      </main>

      {/* 5. Minimal Footer */}
      <footer className="bg-white border-t border-warm-200 py-1.5 px-3 sm:px-4 lg:px-6 text-center text-[11px] text-warm-400 font-mono">
        <div className="w-full max-w-[2560px] 2xl:max-w-[3400px] mx-auto flex flex-wrap items-center justify-between gap-1">
          <span>Market Insight Engine (MIE) · 阶段七：模块化行情数据获取系统与更新编排</span>
          <span>高DPI与全分辨率自适应 · 计算内核: Polars Vectorized · 架构: React 19 + Canvas + FastAPI</span>
        </div>
      </footer>

      {/* 6. Active Data Acquisition & Updating Modal */}
      <DataUpdateModal
        isOpen={isUpdateModalOpen}
        onClose={() => setIsUpdateModalOpen(false)}
        currentSymbol={selectedSymbol}
        onTaskCreated={(tid) => {
          setActiveTaskId(tid);
          setIsTaskMonitorOpen(true);
        }}
      />

      {/* 7. Task Monitor & Heartbeat Drawer */}
      <TaskMonitorDrawer
        isOpen={isTaskMonitorOpen}
        onClose={() => setIsTaskMonitorOpen(false)}
        activeTaskId={activeTaskId}
        onSelectTaskId={setActiveTaskId}
        onTaskCompleted={() => {
          loadMarketData();
        }}
      />
    </div>
  );
};

export default App;
