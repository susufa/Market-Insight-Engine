import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, ChartCandlestick, Loader2 } from 'lucide-react';
import type {
  AdjustType,
  ColorScheme,
  IndicatorRow,
  SubChartIndicator,
  Timeframe,
} from '../types';
import { useElementSize } from '../hooks/useDisplay';
import { clamp, fmtAmount, fmtDate, fmtPct, fmtPrice, fmtVolume, isNum } from '../lib/format';

type Overlay = 'MA' | 'EMA' | 'BOLL' | 'NONE';

interface ChartWorkspaceProps {
  bars: IndicatorRow[];
  timeframe: Timeframe;
  adjType: AdjustType;
  colorScheme: ColorScheme;
  symbol: string;
  qualityStatus: string;
  isLoading: boolean;
  viewKey: string;
  onTimeframeChange: (tf: Timeframe) => void;
  onAdjTypeChange: (adj: AdjustType) => void;
  onColorSchemeChange: (cs: ColorScheme) => void;
}

const MONO = '"Cascadia Mono","SFMono-Regular",Menlo,Consolas,monospace';

const MA_STYLE: Array<{ key: keyof IndicatorRow; label: string; color: string }> = [
  { key: 'ma_5', label: 'MA5', color: '#2D6C8E' },
  { key: 'ma_10', label: 'MA10', color: '#B4552E' },
  { key: 'ma_20', label: 'MA20', color: '#9A7B2F' },
  { key: 'ma_60', label: 'MA60', color: '#7A7480' },
];

const EMA_STYLE: Array<{ key: keyof IndicatorRow; label: string; color: string }> = [
  { key: 'ema_12', label: 'EMA12', color: '#2D6C8E' },
  { key: 'ema_26', label: 'EMA26', color: '#B4552E' },
];

const BOLL_STYLE: Array<{ key: keyof IndicatorRow; label: string; color: string }> = [
  { key: 'boll_upper', label: 'UP', color: '#9A7B2F' },
  { key: 'boll_mid', label: 'MID', color: '#2D6C8E' },
  { key: 'boll_lower', label: 'LOW', color: '#9A7B2F' },
];

const SUB_TABS: SubChartIndicator[] = ['VOL', 'MACD', 'RSI', 'KDJ', 'ATR'];

const TIMEFRAMES: Array<{ id: Timeframe; label: string }> = [
  { id: '1d', label: '日' },
  { id: '1w', label: '周' },
  { id: '1M', label: '月' },
  { id: '1Q', label: '季' },
  { id: '1Y', label: '年' },
];

const ADJUSTS: Array<{ id: AdjustType; label: string }> = [
  { id: 'none', label: '不复权' },
  { id: 'qfq', label: '前复权' },
  { id: 'hfq', label: '后复权' },
];

const OVERLAYS: Array<{ id: Overlay; label: string }> = [
  { id: 'MA', label: 'MA' },
  { id: 'EMA', label: 'EMA' },
  { id: 'BOLL', label: 'BOLL' },
  { id: 'NONE', label: '无' },
];

function overlaySeries(overlay: Overlay) {
  if (overlay === 'MA') return MA_STYLE;
  if (overlay === 'EMA') return EMA_STYLE;
  if (overlay === 'BOLL') return BOLL_STYLE;
  return [];
}

export const ChartWorkspace: React.FC<ChartWorkspaceProps> = ({
  bars,
  timeframe,
  adjType,
  colorScheme,
  symbol,
  qualityStatus,
  isLoading,
  viewKey,
  onTimeframeChange,
  onAdjTypeChange,
  onColorSchemeChange,
}) => {
  const { ref: stageRef, size } = useElementSize<HTMLDivElement>();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const [overlay, setOverlay] = useState<Overlay>('MA');
  const [sub, setSub] = useState<SubChartIndicator>('VOL');
  const [visibleCount, setVisibleCount] = useState(90);
  const [offset, setOffset] = useState(0);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);

  const dragRef = useRef<{ active: boolean; startX: number; startOffset: number }>({
    active: false,
    startX: 0,
    startOffset: 0,
  });
  const zoomedRef = useRef(false);

  const upColor = colorScheme === 'CN' ? '#DC2626' : '#16A34A';
  const downColor = colorScheme === 'CN' ? '#16A34A' : '#DC2626';

  const total = bars.length;
  const count = clamp(visibleCount, 15, Math.max(15, total));
  const maxOffset = Math.max(0, total - count);
  const safeOffset = clamp(offset, 0, maxOffset);
  const end = Math.max(0, total - safeOffset);
  const start = Math.max(0, end - count);

  const visibleBars = useMemo(() => bars.slice(start, end), [bars, start, end]);

  // Reset viewport when the instrument / timeframe / adjustment changes.
  useEffect(() => {
    zoomedRef.current = false;
    setOffset(0);
    setHoverIndex(null);
  }, [viewKey]);

  // Auto-fit bar density to the plot width until the user zooms manually.
  useEffect(() => {
    if (size.width <= 0) return;
    if (zoomedRef.current) return;
    const guess = Math.round(size.width / 16);
    setVisibleCount(clamp(guess, 45, 220));
  }, [size.width, viewKey, total]);

  // Keep zoom window inside data bounds.
  useEffect(() => {
    if (total > 0) setVisibleCount((c) => clamp(c, 15, total));
  }, [total]);

  const hoverBar = hoverIndex !== null ? visibleBars[hoverIndex] : undefined;
  const legendBar = hoverBar ?? visibleBars[visibleBars.length - 1];
  const series = useMemo(() => overlaySeries(overlay), [overlay]);
  const span = visibleBars.length;
  const rangeLabel =
    span > 0 ? fmtDate(visibleBars[0].ts) + ' → ' + fmtDate(visibleBars[span - 1].ts) : '—';

  /* ------------------------------------------------------------------ */
  /* Canvas rendering                                                     */
  /* ------------------------------------------------------------------ */

  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const width = size.width;
    const height = size.height;
    if (width < 60 || height < 60) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const bw = Math.round(width * dpr);
    const bh = Math.round(height * dpr);
    if (canvas.width !== bw || canvas.height !== bh) {
      canvas.width = bw;
      canvas.height = bh;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, width, height);

    const fs = parseFloat(getComputedStyle(document.documentElement).fontSize) || 14;
    const axisW = Math.max(46, fs * 3.55);
    const x0 = fs * 0.35;
    const x1 = width - axisW;
    const dateH = fs * 1.2;
    const plotTop = fs * 1.3;
    const plotBottom = height - dateH;
    if (plotBottom - plotTop < 50) return;

    const gap = fs * 0.45;
    const plotH = plotBottom - plotTop;
    const subH = clamp(plotH * 0.25, fs * 2.4, plotH * 0.4);
    const priceTop = plotTop;
    const priceBottom = plotBottom - subH - gap;
    const subTop = priceBottom + gap;
    const subBottom = plotBottom;
    const priceH = priceBottom - priceTop;
    if (priceH < 40) return;

    const labelPx = (fs * 0.64).toFixed(1) + 'px ';
    ctx.font = '500 ' + labelPx + MONO;
    ctx.textBaseline = 'middle';

    // Empty state is rendered as DOM (crisper type); the canvas stays blank.
    if (visibleBars.length === 0) return;

    // ---- price range -------------------------------------------------
    let min = Infinity;
    let max = -Infinity;
    for (const bar of visibleBars) {
      if (bar.low < min) min = bar.low;
      if (bar.high > max) max = bar.high;
      for (const s of series) {
        const v = bar[s.key];
        if (isNum(v)) {
          if (v < min) min = v;
          if (v > max) max = v;
        }
      }
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) return;
    const padY = (max - min) * 0.07 || Math.max(max * 0.01, 0.01);
    min -= padY;
    max += padY;
    if (min <= 0) min = Math.min(0.01, max * 0.01);
    const priceY = (value: number) => priceBottom - ((value - min) / (max - min)) * priceH;

    // ---- sub range ---------------------------------------------------
    let subMin = 0;
    let subMax = 1;
    if (sub === 'VOL') {
      subMax = 1;
      for (const bar of visibleBars) subMax = Math.max(subMax, bar.volume);
      subMin = 0;
    } else if (sub === 'MACD') {
      let peak = 0.0001;
      for (const bar of visibleBars) {
        for (const key of ['macd_dif', 'macd_dea', 'macd_hist'] as const) {
          const v = bar[key];
          if (isNum(v)) peak = Math.max(peak, Math.abs(v));
        }
      }
      subMax = peak * 1.15;
      subMin = -subMax;
    } else if (sub === 'RSI' || sub === 'KDJ') {
      subMin = 0;
      subMax = 100;
    } else {
      let lo = Infinity;
      let hi = -Infinity;
      for (const bar of visibleBars) {
        const v = bar.atr_14;
        if (isNum(v)) {
          lo = Math.min(lo, v);
          hi = Math.max(hi, v);
        }
      }
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
        lo = 0;
        hi = 1;
      }
      subMin = Math.max(0, lo * 0.85);
      subMax = hi * 1.1 || 1;
    }
    const subY = (value: number) =>
      subBottom - ((clamp(value, subMin, subMax) - subMin) / (subMax - subMin || 1)) * subH;

    const barSpace = (x1 - x0) / visibleBars.length;
    const bodyW = clamp(barSpace * 0.62, 1, fs * 0.9);
    const cx = (i: number) => x0 + i * barSpace + barSpace / 2;

    // ---- horizontal grid + price axis --------------------------------
    const steps = priceH > 300 ? 6 : priceH > 180 ? 5 : 4;
    ctx.setLineDash([1, 4]);
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#F0ECE3';
    ctx.fillStyle = '#A6A198';
    ctx.textAlign = 'left';
    for (let i = 0; i <= steps; i++) {
      const y = Math.round(priceTop + (priceH / steps) * i) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();
      const value = max - ((max - min) / steps) * i;
      ctx.fillText(fmtPrice(value), x1 + fs * 0.4, y);
    }
    ctx.setLineDash([]);

    // ---- date ticks + vertical grid ----------------------------------
    const tickCount = clamp(Math.floor((x1 - x0) / (fs * 7.2)), 3, 12);
    const tickStep = Math.max(1, Math.floor(visibleBars.length / tickCount));
    ctx.strokeStyle = '#F5F2EC';
    ctx.setLineDash([1, 5]);
    for (let i = visibleBars.length - 1; i >= 0; i -= tickStep) {
      const x = Math.round(cx(i)) + 0.5;
      if (x < x0 || x > x1) continue;
      ctx.beginPath();
      ctx.moveTo(x, priceTop);
      ctx.lineTo(x, priceBottom);
      ctx.moveTo(x, subTop);
      ctx.lineTo(x, subBottom);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.fillStyle = '#A6A198';
    ctx.textAlign = 'center';
    for (let i = visibleBars.length - 1; i >= 0; i -= tickStep) {
      const x = cx(i);
      if (x < x0 + fs || x > x1 - fs) continue;
      ctx.fillText(fmtDate(visibleBars[i].ts), x, height - dateH / 2);
    }

    // ---- candles ------------------------------------------------------
    for (let i = 0; i < visibleBars.length; i++) {
      const bar = visibleBars[i];
      const up = bar.close >= bar.open;
      const color = up ? upColor : downColor;
      const x = Math.round(cx(i)) + 0.5;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = Math.max(1, Math.min(1.6, barSpace * 0.12));
      ctx.beginPath();
      ctx.moveTo(x, priceY(bar.high));
      ctx.lineTo(x, priceY(bar.low));
      ctx.stroke();
      const yOpen = priceY(bar.open);
      const yClose = priceY(bar.close);
      const top = Math.min(yOpen, yClose);
      const h = Math.max(1, Math.abs(yClose - yOpen));
      ctx.fillRect(Math.round(cx(i) - bodyW / 2), top, Math.max(1, Math.round(bodyW)), h);
    }

    // ---- overlays -----------------------------------------------------
    const drawLine = (
      key: keyof IndicatorRow,
      color: string,
      widthPx: number,
      area: 'price' | 'sub' = 'price',
      dash: number[] = [],
    ) => {
      const map = area === 'price' ? priceY : subY;
      ctx.strokeStyle = color;
      ctx.lineWidth = widthPx;
      ctx.setLineDash(dash);
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < visibleBars.length; i++) {
        const raw = visibleBars[i][key];
        if (!isNum(raw)) {
          started = false;
          continue;
        }
        const x = cx(i);
        const y = map(raw);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.setLineDash([]);
    };

    if (series.length > 0) {
      for (const s of series) {
        drawLine(s.key, s.color, 1.25, 'price', overlay === 'BOLL' && s.label !== 'MID' ? [3, 3] : []);
      }
    }

    // ---- sub chart ----------------------------------------------------
    ctx.strokeStyle = '#EDE9E0';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x0, Math.round(subBottom) + 0.5);
    ctx.lineTo(x1, Math.round(subBottom) + 0.5);
    ctx.stroke();

    if (sub === 'VOL') {
      for (let i = 0; i < visibleBars.length; i++) {
        const bar = visibleBars[i];
        const up = bar.close >= bar.open;
        const y = subY(bar.volume);
        ctx.fillStyle = up ? upColor : downColor;
        ctx.globalAlpha = 0.55;
        ctx.fillRect(Math.round(cx(i) - bodyW / 2), y, Math.max(1, Math.round(bodyW)), Math.max(1, subBottom - y));
        ctx.globalAlpha = 1;
      }
      ctx.fillStyle = '#A6A198';
      ctx.textAlign = 'left';
      ctx.fillText(fmtVolume(subMax), x1 + fs * 0.4, subTop + fs * 0.4);
    } else if (sub === 'MACD') {
      const zero = subY(0);
      ctx.strokeStyle = '#DFD9CE';
      ctx.setLineDash([2, 3]);
      ctx.beginPath();
      ctx.moveTo(x0, Math.round(zero) + 0.5);
      ctx.lineTo(x1, Math.round(zero) + 0.5);
      ctx.stroke();
      ctx.setLineDash([]);
      for (let i = 0; i < visibleBars.length; i++) {
        const hist = visibleBars[i].macd_hist;
        if (!isNum(hist)) continue;
        const y = subY(hist);
        ctx.fillStyle = hist >= 0 ? upColor : downColor;
        ctx.globalAlpha = 0.55;
        ctx.fillRect(Math.round(cx(i) - bodyW / 2), Math.min(y, zero), Math.max(1, Math.round(bodyW)), Math.max(1, Math.abs(zero - y)));
        ctx.globalAlpha = 1;
      }
      drawLine('macd_dif', '#2D6C8E', 1.2, 'sub');
      drawLine('macd_dea', '#B4552E', 1.2, 'sub');
    } else if (sub === 'RSI') {
      for (const level of [20, 80]) {
        const y = Math.round(subY(level)) + 0.5;
        ctx.strokeStyle = '#E7E1D6';
        ctx.setLineDash([2, 3]);
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(x1, y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#A6A198';
        ctx.textAlign = 'left';
        ctx.fillText(String(level), x1 + fs * 0.4, y);
      }
      drawLine('rsi_6', '#2D6C8E', 1.2, 'sub');
      drawLine('rsi_12', '#9A7B2F', 1.2, 'sub');
      drawLine('rsi_24', '#7A7480', 1.2, 'sub');
    } else if (sub === 'KDJ') {
      for (const level of [20, 80]) {
        const y = Math.round(subY(level)) + 0.5;
        ctx.strokeStyle = '#E7E1D6';
        ctx.setLineDash([2, 3]);
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(x1, y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      drawLine('kdj_k', '#2D6C8E', 1.2, 'sub');
      drawLine('kdj_d', '#9A7B2F', 1.2, 'sub');
      drawLine('kdj_j', '#B4552E', 1.2, 'sub');
    } else {
      drawLine('atr_14', '#7A7480', 1.3, 'sub');
      ctx.fillStyle = '#A6A198';
      ctx.textAlign = 'left';
      ctx.fillText(fmtPrice(subMax), x1 + fs * 0.4, subTop + fs * 0.4);
    }

    // ---- last close marker -------------------------------------------
    const last = visibleBars[visibleBars.length - 1];
    if (!hoverBar) {
      const y = priceY(last.close);
      ctx.strokeStyle = upColor;
      ctx.globalAlpha = 0.28;
      ctx.setLineDash([3, 4]);
      ctx.beginPath();
      ctx.moveTo(x0, Math.round(y) + 0.5);
      ctx.lineTo(x1, Math.round(y) + 0.5);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      const tag = fmtPrice(last.close);
      const color = last.close >= last.open ? upColor : downColor;
      ctx.font = '600 ' + (fs * 0.64).toFixed(1) + 'px ' + MONO;
      const tw = ctx.measureText(tag).width + fs * 0.55;
      const th = fs * 0.98;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.roundRect(x1 + 3, y - th / 2, Math.min(tw, axisW - 4), th, 2);
      ctx.fill();
      ctx.fillStyle = '#FFFFFF';
      ctx.textAlign = 'left';
      ctx.fillText(tag, x1 + 3 + fs * 0.28, y + 0.5);
    }

    // ---- crosshair ----------------------------------------------------
    if (hoverBar && cursor) {
      const x = Math.round(cx(hoverIndex as number)) + 0.5;
      ctx.strokeStyle = '#4D4A45';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, plotTop);
      ctx.lineTo(x, plotBottom);
      ctx.stroke();

      const inPrice = cursor.y <= priceBottom;
      const yLine = inPrice ? cursor.y : clamp(cursor.y, subTop, subBottom);
      ctx.beginPath();
      ctx.moveTo(x0, Math.round(yLine) + 0.5);
      ctx.lineTo(x1, Math.round(yLine) + 0.5);
      ctx.stroke();
      ctx.setLineDash([]);

      // axis value tag
      let tagText = '';
      if (inPrice) {
        tagText = fmtPrice(max - ((yLine - priceTop) / priceH) * (max - min));
      } else {
        tagText = fmtPrice(subMin + ((subBottom - yLine) / subH) * (subMax - subMin));
      }
      ctx.font = '500 ' + (fs * 0.64).toFixed(1) + 'px ' + MONO;
      const tw = Math.min(ctx.measureText(tagText).width + fs * 0.55, axisW - 4);
      const th = fs * 0.98;
      ctx.fillStyle = '#33322F';
      ctx.beginPath();
      ctx.roundRect(x1 + 3, yLine - th / 2, tw, th, 2);
      ctx.fill();
      ctx.fillStyle = '#FFFFFF';
      ctx.textAlign = 'left';
      ctx.fillText(tagText, x1 + 3 + fs * 0.28, yLine + 0.5);

      // date tag
      const dtext = fmtDate(hoverBar.ts);
      const dw = ctx.measureText(dtext).width + fs * 0.7;
      const dx = clamp(x - dw / 2, x0, x1 - dw);
      ctx.fillStyle = '#33322F';
      ctx.beginPath();
      ctx.roundRect(dx, height - dateH + 1, dw, dateH - 3, 2);
      ctx.fill();
      ctx.fillStyle = '#FFFFFF';
      ctx.textAlign = 'center';
      ctx.fillText(dtext, dx + dw / 2, height - dateH / 2);
    }
  }, [
    size,
    visibleBars,
    overlay,
    sub,
    series,
    upColor,
    downColor,
    hoverBar,
    hoverIndex,
    cursor,
    isLoading,
  ]);

  useEffect(() => {
    render();
  }, [render]);

  // Redraw when the display profile changes (window resize, browser zoom, DPR move).
  useEffect(() => {
    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(render);
    };
    window.addEventListener('resize', schedule);
    const mq = window.matchMedia('(resolution: ' + (window.devicePixelRatio || 1) + 'dppx)');
    const onDpr = () => {
      schedule();
    };
    try {
      mq.addEventListener('change', onDpr);
    } catch {
      mq.addListener(onDpr);
    }
    return () => {
      window.removeEventListener('resize', schedule);
      cancelAnimationFrame(frame);
      try {
        mq.removeEventListener('change', onDpr);
      } catch {
        mq.removeListener(onDpr);
      }
    };
  }, [render]);

  // Wheel zoom must be non-passive to prevent page scroll.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      zoomedRef.current = true;
      setVisibleCount((prev) => {
        const next = event.deltaY < 0 ? prev - 6 : prev + 6;
        return clamp(next, 15, Math.max(15, bars.length));
      });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [bars.length]);

  const locate = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const fs = parseFloat(getComputedStyle(document.documentElement).fontSize) || 14;
    const axisW = Math.max(46, fs * 3.55);
    const x0 = fs * 0.35;
    const x1 = rect.width - axisW;
    if (x < x0 || x > x1 || visibleBars.length === 0) return { x, y, index: null as number | null };
    const barSpace = (x1 - x0) / visibleBars.length;
    const index = clamp(Math.floor((x - x0) / barSpace), 0, visibleBars.length - 1);
    return { x, y, index };
  };

  const onPointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.setPointerCapture(event.pointerId);
    dragRef.current = { active: true, startX: event.clientX, startOffset: safeOffset };
  };

  const onPointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const hit = locate(event.clientX, event.clientY);
    if (!hit) return;
    setCursor({ x: hit.x, y: hit.y });
    setHoverIndex(hit.index);
    if (dragRef.current.active) {
      const fs = parseFloat(getComputedStyle(document.documentElement).fontSize) || 14;
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const axisW = Math.max(46, fs * 3.55);
      const x0 = fs * 0.35;
      const x1 = rect.width - axisW;
      const barSpace = (x1 - x0) / Math.max(1, visibleBars.length);
      const shift = Math.round((event.clientX - dragRef.current.startX) / barSpace);
      setOffset(
        clamp(dragRef.current.startOffset + shift, 0, Math.max(0, bars.length - visibleBars.length)),
      );
    }
  };

  const endDrag = (event: React.PointerEvent<HTMLCanvasElement>) => {
    dragRef.current.active = false;
    try {
      canvasRef.current?.releasePointerCapture(event.pointerId);
    } catch {
      /* pointer already released */
    }
  };

  const resetView = () => {
    zoomedRef.current = false;
    setOffset(0);
    setVisibleCount(clamp(Math.round(size.width / 16), 45, 220));
  };

  const zoom = (delta: number) => {
    zoomedRef.current = true;
    setVisibleCount((prev) => clamp(prev + delta, 15, Math.max(15, bars.length)));
  };

  /* ------------------------------------------------------------------ */
  /* Overlay markup                                                       */
  /* ------------------------------------------------------------------ */

  const legendItems = series.map((s) => ({
    label: s.label,
    color: s.color,
    value: legendBar && isNum(legendBar[s.key]) ? fmtPrice(legendBar[s.key] as number) : '—',
  }));

  const subLegend = (() => {
    const bar = legendBar;
    if (!bar) return [] as Array<{ label: string; color: string; value: string }>;
    if (sub === 'VOL') {
      return [{ label: 'VOL', color: '#9C978E', value: fmtVolume(bar.volume) }];
    }
    if (sub === 'MACD') {
      return [
        { label: 'DIF', color: '#2D6C8E', value: isNum(bar.macd_dif) ? fmtPrice(bar.macd_dif, 3) : '—' },
        { label: 'DEA', color: '#B4552E', value: isNum(bar.macd_dea) ? fmtPrice(bar.macd_dea, 3) : '—' },
        { label: 'HIST', color: '#9C978E', value: isNum(bar.macd_hist) ? fmtPrice(bar.macd_hist, 3) : '—' },
      ];
    }
    if (sub === 'RSI') {
      return [
        { label: 'RSI6', color: '#2D6C8E', value: isNum(bar.rsi_6) ? fmtPrice(bar.rsi_6, 1) : '—' },
        { label: 'RSI12', color: '#9A7B2F', value: isNum(bar.rsi_12) ? fmtPrice(bar.rsi_12, 1) : '—' },
        { label: 'RSI24', color: '#7A7480', value: isNum(bar.rsi_24) ? fmtPrice(bar.rsi_24, 1) : '—' },
      ];
    }
    if (sub === 'KDJ') {
      return [
        { label: 'K', color: '#2D6C8E', value: isNum(bar.kdj_k) ? fmtPrice(bar.kdj_k, 1) : '—' },
        { label: 'D', color: '#9A7B2F', value: isNum(bar.kdj_d) ? fmtPrice(bar.kdj_d, 1) : '—' },
        { label: 'J', color: '#B4552E', value: isNum(bar.kdj_j) ? fmtPrice(bar.kdj_j, 1) : '—' },
      ];
    }
    return [{ label: 'ATR14', color: '#7A7480', value: isNum(bar.atr_14) ? fmtPrice(bar.atr_14) : '—' }];
  })();

  // Vertical placement of the sub legend mirrors the canvas geometry above.
  const fs = parseFloat(getComputedStyle(document.documentElement).fontSize) || 14;
  const geoDateH = fs * 1.2;
  const geoPlotH = size.height - geoDateH - fs * 1.3;
  const geoSubH = clamp(geoPlotH * 0.25, fs * 2.4, geoPlotH * 0.4);
  const subLegendTop = size.height - geoDateH - geoSubH + fs * 0.18;

  const prevBarClose =
    hoverIndex !== null && hoverIndex > 0 ? visibleBars[hoverIndex - 1]?.close ?? null : null;
  const tooltipChange = hoverBar
    ? prevBarClose && prevBarClose !== 0
      ? ((hoverBar.close - prevBarClose) / prevBarClose) * 100
      : ((hoverBar.close - hoverBar.open) / (hoverBar.open || 1)) * 100
    : 0;

  const tooltipStyle: React.CSSProperties | undefined = (() => {
    if (!hoverBar || !cursor || size.width === 0) return undefined;
    const width = 13.2 * fs;
    const estimated = 11.4 * fs;
    const left = clamp(cursor.x + fs * 0.9, 6, Math.max(6, size.width - width - 6));
    const top =
      cursor.y + estimated + 8 > size.height
        ? clamp(cursor.y - estimated - 6, 6, Math.max(6, size.height - estimated - 6))
        : cursor.y + fs * 0.8;
    return { left, top };
  })();

  return (
    <section className="card chart-card" aria-label="K 线工作区">
      <div className="chart-toolbar">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <div className="toolbar-group">
            <span className="toolbar-label">周期</span>
            <div className="seg">
              {TIMEFRAMES.map((t) => (
                <button
                  type="button"
                  key={t.id}
                  className="seg__item"
                  data-active={timeframe === t.id}
                  onClick={() => onTimeframeChange(t.id)}
                  title={'周期 ' + t.label}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="toolbar-group">
            <span className="toolbar-label">复权</span>
            <div className="seg">
              {ADJUSTS.map((a) => (
                <button
                  type="button"
                  key={a.id}
                  className="seg__item"
                  data-active={adjType === a.id}
                  onClick={() => onAdjTypeChange(a.id)}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </div>

          <div className="toolbar-group">
            <span className="toolbar-label hidden xl:inline">主图</span>
            <div className="seg">
              {OVERLAYS.map((o) => (
                <button
                  type="button"
                  key={o.id}
                  className="seg__item"
                  data-active={overlay === o.id}
                  onClick={() => setOverlay(o.id)}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <div className="toolbar-group">
            <span className="toolbar-label hidden xl:inline">副图</span>
            <div className="seg">
              {SUB_TABS.map((id) => (
                <button
                  type="button"
                  key={id}
                  className="seg__item"
                  data-active={sub === id}
                  onClick={() => setSub(id)}
                >
                  {id}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => onColorSchemeChange(colorScheme === 'CN' ? 'INTL' : 'CN')}
            title="切换涨跌配色"
          >
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: upColor }}
            />
            <span>{colorScheme === 'CN' ? '红涨' : '绿涨'}</span>
          </button>

          <div className="toolbar-group">
            <button
              type="button"
              className="icon-btn"
              onClick={() => zoom(-12)}
              title="放大（更少 K 线）"
              aria-label="放大"
            >
              <ZoomIn size={13} />
            </button>
            <button
              type="button"
              className="icon-btn"
              onClick={() => zoom(12)}
              title="缩小（更多 K 线）"
              aria-label="缩小"
            >
              <ZoomOut size={13} />
            </button>
            <button
              type="button"
              className="icon-btn"
              onClick={resetView}
              title="复位视图"
              aria-label="复位视图"
            >
              <RotateCcw size={13} />
            </button>
          </div>
        </div>
      </div>

      <div className="chart-stage" ref={stageRef}>
        <div className="chart-canvas-wrap" ref={wrapRef} style={{ position: 'absolute', inset: 0 }}>
          <canvas
            ref={canvasRef}
            className="chart-canvas"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            onPointerLeave={() => {
              setHoverIndex(null);
              setCursor(null);
            }}
            onDoubleClick={resetView}
          />
        </div>

        {visibleBars.length > 0 && (
          <>
            <div className="chart-legend">
              <span className="legend-item">
                <span className="eyebrow" style={{ color: '#9C978E' }}>
                  {symbol}
                </span>
              </span>
              {legendItems.map((item) => (
                <span className="legend-item" key={item.label}>
                  <span className="legend-swatch" style={{ background: item.color }} />
                  <span style={{ color: '#8C877E' }}>{item.label}</span>
                  <span style={{ color: '#33322F', fontWeight: 500 }}>{item.value}</span>
                </span>
              ))}
              <span className="legend-item chart-range" style={{ marginLeft: 'auto' }}>
                <span style={{ color: '#B4AFA7' }}>{rangeLabel}</span>
              </span>
            </div>

            <div className="chart-sublegend" style={{ top: subLegendTop }}>
              {subLegend.map((item) => (
                <span className="legend-item" key={item.label}>
                  <span className="legend-swatch" style={{ background: item.color }} />
                  <span style={{ color: '#8C877E' }}>{item.label}</span>
                  <span style={{ color: '#33322F', fontWeight: 500 }}>{item.value}</span>
                </span>
              ))}
            </div>
          </>
        )}

        {visibleBars.length === 0 && !isLoading && (
          <div className="empty-state">
            <div className="empty-state__badge">
              <ChartCandlestick size={16} strokeWidth={1.6} />
            </div>
            <div className="empty-state__title">暂无本地真实行情</div>
            <div className="empty-state__hint">
              该标的尚未入库，或本地存储未通过质量校验（{qualityStatus}）。系统严格禁止展示合成演示 K 线。
            </div>
          </div>
        )}

        {isLoading && (
          <div className="absolute inset-x-0 top-0 z-10 flex items-center gap-1.5 bg-white/85 px-2 py-1">
            <Loader2 size={11} className="spin text-warm-500" />
            <span className="eyebrow">LOADING · 正在读取本地存储</span>
          </div>
        )}
        {isLoading && <div className="load-bar" />}

        {hoverBar && cursor && tooltipStyle && (
          <div className="chart-tooltip" style={tooltipStyle}>
            <div className="tip-row">
              <span className="tip-row__k">日期</span>
              <span className="tip-row__v">{fmtDate(hoverBar.ts)}</span>
            </div>
            <div className="tip-sep" />
            <div className="tip-row">
              <span className="tip-row__k">开</span>
              <span className="tip-row__v">{fmtPrice(hoverBar.open)}</span>
            </div>
            <div className="tip-row">
              <span className="tip-row__k">高</span>
              <span className="tip-row__v">{fmtPrice(hoverBar.high)}</span>
            </div>
            <div className="tip-row">
              <span className="tip-row__k">低</span>
              <span className="tip-row__v">{fmtPrice(hoverBar.low)}</span>
            </div>
            <div className="tip-row">
              <span className="tip-row__k">收</span>
              <span
                className="tip-row__v"
                style={{ color: hoverBar.close >= hoverBar.open ? upColor : downColor }}
              >
                {fmtPrice(hoverBar.close)}
              </span>
            </div>
            <div className="tip-row">
              <span className="tip-row__k">涨跌</span>
              <span
                className="tip-row__v"
                style={{ color: hoverBar.close >= hoverBar.open ? upColor : downColor }}
              >
                {fmtPct(tooltipChange)}
              </span>
            </div>
            <div className="tip-sep" />
            <div className="tip-row">
              <span className="tip-row__k">成交量</span>
              <span className="tip-row__v">{fmtVolume(hoverBar.volume)}</span>
            </div>
            {isNum(hoverBar.amount) && (
              <div className="tip-row">
                <span className="tip-row__k">成交额</span>
                <span className="tip-row__v">{fmtAmount(hoverBar.amount)}</span>
              </div>
            )}
            {legendItems.map((item) => (
              <div className="tip-row" key={item.label}>
                <span className="tip-row__k">{item.label}</span>
                <span className="tip-row__v">{item.value}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};
