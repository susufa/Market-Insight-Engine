import React, { useCallback, useEffect, useRef, useState } from 'react';
import { TopBar } from './components/TopBar';
import { QuoteBoard } from './components/QuoteBoard';
import { ChartWorkspace } from './components/ChartWorkspace';
import { ContextRail } from './components/ContextRail';
import { InsightDock } from './components/InsightDock';
import { DataUpdateDialog } from './components/DataUpdateDialog';
import { TaskDrawer } from './components/TaskDrawer';
import type {
  AdjustType,
  BreadthReport,
  ColorScheme,
  HealthState,
  IndexQuote,
  IndicatorRow,
  ModelEvaluationSummary,
  PredictionResult,
  QuoteResponse,
  RelativePerformance,
  SectorSummary,
  Security,
  Timeframe,
} from './types';
import {
  fetchBars,
  fetchForecast,
  fetchHealth,
  fetchIndicators,
  fetchMarketBreadth,
  fetchQuote,
  fetchRelativePerformance,
  fetchSectors,
  fetchSecurities,
  fetchWalkForwardReport,
} from './api';
import { useDisplayProfile } from './hooks/useDisplay';
import { fmtClock } from './lib/format';

const INDEX_DEFS: Array<{ symbol: string; label: string }> = [
  { symbol: '000001.SH', label: '上证指数' },
  { symbol: '399001.SZ', label: '深证成指' },
  { symbol: '399006.SZ', label: '创业板指' },
  { symbol: 'HSI.HK', label: '恒生指数' },
];

const COLOR_KEY = 'mie.colorScheme';

function readColorScheme(): ColorScheme {
  try {
    return localStorage.getItem(COLOR_KEY) === 'INTL' ? 'INTL' : 'CN';
  } catch {
    return 'CN';
  }
}

export const App: React.FC = () => {
  const [selectedSymbol, setSelectedSymbol] = useState('600519.SH');
  const [timeframe, setTimeframe] = useState<Timeframe>('1d');
  const [adjType, setAdjType] = useState<AdjustType>('none');
  const [colorScheme, setColorScheme] = useState<ColorScheme>(readColorScheme);

  const [securities, setSecurities] = useState<Security[]>([]);
  const [quote, setQuote] = useState<QuoteResponse | null>(null);
  const [bars, setBars] = useState<IndicatorRow[]>([]);
  const [breadth, setBreadth] = useState<BreadthReport | null>(null);
  const [sectors, setSectors] = useState<SectorSummary[]>([]);
  const [relative, setRelative] = useState<RelativePerformance | null>(null);
  const [prediction, setPrediction] = useState<PredictionResult | null>(null);
  const [walkForward, setWalkForward] = useState<ModelEvaluationSummary | null>(null);

  const [qualityStatus, setQualityStatus] = useState('NO_DATA');
  const [isCached, setIsCached] = useState(false);
  const [dataOrigin, setDataOrigin] = useState('unknown');
  const [sourceInterface, setSourceInterface] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);

  const [indices, setIndices] = useState<IndexQuote[]>(
    INDEX_DEFS.map((d) => ({ ...d, price: null, pct: null })),
  );
  const [health, setHealth] = useState<HealthState>('checking');

  const [updateOpen, setUpdateOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);

  const [pageRatio, setPageRatio] = useState(1);
  const display = useDisplayProfile();
  const requestId = useRef(0);

  const security = securities.find((s) => s.symbol === selectedSymbol);
  const latestIndicator = bars.length > 0 ? bars[bars.length - 1] : null;
  const viewKey = selectedSymbol + ':' + timeframe + ':' + adjType;

  /* ---- colour scheme persistence -------------------------------------- */
  useEffect(() => {
    try {
      localStorage.setItem(COLOR_KEY, colorScheme);
    } catch {
      /* private mode */
    }
  }, [colorScheme]);

  /* ---- one-off catalogue & macro -------------------------------------- */
  useEffect(() => {
    let alive = true;
    fetchSecurities(undefined, undefined, 500).then((res) => {
      if (alive) setSecurities(res.items ?? []);
    });
    fetchMarketBreadth('CN_A').then((data) => {
      if (alive) setBreadth(data);
    });
    fetchSectors('000001.SH').then((data) => {
      if (alive) setSectors(data);
    });
    return () => {
      alive = false;
    };
  }, []);

  /* ---- health probe ---------------------------------------------------- */
  const probeHealth = useCallback(async () => {
    const res = await fetchHealth();
    setHealth(res ? 'live' : 'offline');
  }, []);

  useEffect(() => {
    void probeHealth();
    const timer = window.setInterval(() => {
      void probeHealth();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [probeHealth]);

  /* ---- index strip ----------------------------------------------------- */
  const loadIndices = useCallback(async () => {
    const results = await Promise.allSettled(INDEX_DEFS.map((d) => fetchQuote(d.symbol)));
    setIndices(
      INDEX_DEFS.map((def, i) => {
        const result = results[i];
        const q = result.status === 'fulfilled' ? result.value : null;
        return {
          ...def,
          price: q?.last_price ?? null,
          pct: q?.pct_change ?? null,
          asOf: q?.ts ?? null,
        };
      }),
    );
  }, []);

  useEffect(() => {
    void loadIndices();
  }, [loadIndices]);

  /* ---- instrument market data ----------------------------------------- */
  const loadMarket = useCallback(async () => {
    const ticket = ++requestId.current;
    setIsLoading(true);
    try {
      const [quoteRes, indRes, perfRes, predRes, wfRes] = await Promise.all([
        fetchQuote(selectedSymbol),
        fetchIndicators(selectedSymbol, timeframe, adjType),
        fetchRelativePerformance(selectedSymbol, '000001.SH'),
        fetchForecast(selectedSymbol),
        fetchWalkForwardReport(selectedSymbol),
      ]);

      if (ticket !== requestId.current) return;

      setQuote(quoteRes);
      setDataOrigin(quoteRes?.data_origin ?? 'unknown');
      setSourceInterface(quoteRes?.source_interface ?? '');

      if (indRes && indRes.rows.length > 0) {
        setBars(indRes.rows);
        setIsCached(indRes.is_cached);
        setQualityStatus('PASS');
      } else {
        const fallback = await fetchBars(selectedSymbol, timeframe, adjType);
        if (ticket !== requestId.current) return;
        setBars(fallback.bars as IndicatorRow[]);
        setIsCached(fallback.is_cached);
        setQualityStatus(fallback.data_quality_status);
        if (fallback.data_origin) setDataOrigin(fallback.data_origin);
        if (fallback.source_interface) setSourceInterface(fallback.source_interface);
      }

      setRelative(perfRes);
      setPrediction(predRes);
      setWalkForward(wfRes);
      setLastLoadedAt(new Date().toISOString());
    } catch (err) {
      console.warn('market data load failed', err);
    } finally {
      if (ticket === requestId.current) setIsLoading(false);
    }
  }, [selectedSymbol, timeframe, adjType]);

  useEffect(() => {
    void loadMarket();
  }, [loadMarket]);

  const refreshAll = useCallback(() => {
    void loadMarket();
    void loadIndices();
    void probeHealth();
    void fetchMarketBreadth('CN_A').then(setBreadth);
    void fetchSectors('000001.SH').then(setSectors);
  }, [loadMarket, loadIndices, probeHealth]);

  /* ---- honest page-height gauge (target ≤ 1.5 screens) ---------------- */
  useEffect(() => {
    const measure = () => {
      const doc = document.documentElement;
      const ratio = doc.scrollHeight / Math.max(1, window.innerHeight);
      setPageRatio(Math.round(Math.min(9.99, ratio) * 100) / 100);
    };
    measure();
    const timer = window.setTimeout(measure, 240);
    window.addEventListener('resize', measure);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('resize', measure);
    };
  }, [isLoading, drawerOpen, updateOpen]);

  const onTaskCompleted = useCallback(() => {
    void loadMarket();
    void loadIndices();
  }, [loadMarket, loadIndices]);

  return (
    <div className="app-shell">
      <TopBar
        indices={indices}
        securities={securities}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={setSelectedSymbol}
        health={health}
        isRefreshing={isLoading}
        onRefresh={refreshAll}
      />

      <QuoteBoard
        security={security}
        quote={quote}
        colorScheme={colorScheme}
        isCached={isCached}
        qualityStatus={qualityStatus}
        dataOrigin={dataOrigin}
        sourceInterface={sourceInterface}
        isLoading={isLoading}
        activeTaskCount={activeTaskId || drawerOpen ? 1 : 0}
        onOpenUpdate={() => setUpdateOpen(true)}
        onOpenMonitor={() => setDrawerOpen(true)}
        onRefresh={loadMarket}
      />

      <main className="flex min-h-0 flex-1 flex-col">
        <div className="shell-bleed workspace">
          <ChartWorkspace
            bars={bars}
            timeframe={timeframe}
            adjType={adjType}
            colorScheme={colorScheme}
            symbol={selectedSymbol}
            qualityStatus={qualityStatus}
            isLoading={isLoading}
            viewKey={viewKey}
            onTimeframeChange={setTimeframe}
            onAdjTypeChange={setAdjType}
            onColorSchemeChange={setColorScheme}
          />

          <ContextRail
            quote={quote}
            security={security}
            bars={bars}
            latestIndicator={latestIndicator}
            prediction={prediction}
            colorScheme={colorScheme}
            qualityStatus={qualityStatus}
            isCached={isCached}
            dataOrigin={dataOrigin}
            sourceInterface={sourceInterface}
          />
        </div>
      </main>

      <InsightDock
        quote={quote}
        security={security}
        breadth={breadth}
        sectors={sectors}
        relative={relative}
        latestIndicator={latestIndicator}
        prediction={prediction}
        walkForward={walkForward}
        colorScheme={colorScheme}
        qualityStatus={qualityStatus}
        isCached={isCached}
        dataOrigin={dataOrigin}
        sourceInterface={sourceInterface}
        totalBars={bars.length}
      />

      <footer className="statusbar">
        <div className="statusbar__group">
          <span className="flex items-center gap-1.5">
            <span className={'led ' + (health === 'live' ? 'led--live' : health === 'checking' ? 'led--warn' : 'led--off')} />
            MIE · beta 0.1.0
          </span>
          <span className="statusbar__sep" />
          <span className="hidden sm:inline">本地优先 · FastAPI / Polars / Parquet</span>
          <span className="statusbar__sep hidden sm:inline" />
          <span className="hidden lg:inline">前端重构 · 暖纸终端</span>
        </div>

        <div className="statusbar__group">
          <span className="hidden md:inline">同步 {lastLoadedAt ? fmtClock(lastLoadedAt) : '—'}</span>
          <span className="statusbar__sep hidden md:inline" />
          <span>
            {display.width}×{display.height}
          </span>
          <span className="statusbar__sep" />
          <span>DPR {display.dpr.toFixed(2)}</span>
          <span className="statusbar__sep" />
          <span className={pageRatio > 1.5 ? 'text-market-red' : undefined}>
            页面 {pageRatio.toFixed(2)}× 视口
          </span>
        </div>
      </footer>

      <DataUpdateDialog
        isOpen={updateOpen}
        onClose={() => setUpdateOpen(false)}
        currentSymbol={selectedSymbol}
        onTaskCreated={(taskId) => {
          setActiveTaskId(taskId);
          setDrawerOpen(true);
        }}
      />

      <TaskDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeTaskId={activeTaskId}
        onSelectTaskId={setActiveTaskId}
        onTaskCompleted={onTaskCompleted}
      />
    </div>
  );
};

export default App;
