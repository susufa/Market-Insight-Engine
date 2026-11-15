import React, { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import { IndicatorRow, Timeframe, AdjustType, ColorScheme, SubChartIndicator } from '../types';
import { ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';

interface StockChartProps {
  bars: IndicatorRow[];
  timeframe: Timeframe;
  adjType: AdjustType;
  colorScheme: ColorScheme;
  onTimeframeChange: (tf: Timeframe) => void;
  onAdjTypeChange: (adj: AdjustType) => void;
  onColorSchemeChange: (cs: ColorScheme) => void;
  isLoading: boolean;
}

export const StockChart: React.FC<StockChartProps> = ({
  bars,
  timeframe,
  adjType,
  colorScheme,
  onTimeframeChange,
  onAdjTypeChange,
  onColorSchemeChange,
  isLoading,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Main overlay indicator mode
  const [mainOverlay, setMainOverlay] = useState<'MA' | 'EMA' | 'BOLL' | 'NONE'>('MA');

  // Sub-chart indicator tab
  const [subIndicator, setSubIndicator] = useState<SubChartIndicator>('VOL');

  // Viewport navigation (pan & zoom)
  const [visibleCount, setVisibleCount] = useState(90);
  const [offsetRight, setOffsetRight] = useState(0); // 0 means latest bars
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragStartOffset, setDragStartOffset] = useState(0);

  // Palette according to color scheme
  const upColor = colorScheme === 'CN' ? '#DC2626' : '#16A34A';
  const downColor = colorScheme === 'CN' ? '#16A34A' : '#DC2626';

  // Compute slice of bars currently in view
  const totalBars = bars.length;
  const effectiveCount = Math.min(Math.max(15, visibleCount), totalBars);
  const maxOffset = Math.max(0, totalBars - effectiveCount);
  const effectiveOffset = Math.min(Math.max(0, offsetRight), maxOffset);

  const startIndex = Math.max(0, totalBars - effectiveCount - effectiveOffset);
  const endIndex = Math.min(totalBars, totalBars - effectiveOffset);
  const visibleBars = useMemo(
    () => bars.slice(startIndex, endIndex),
    [bars, startIndex, endIndex]
  );

  // Redraw Canvas on resize or state change
  const renderChart = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !containerRef.current) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = containerRef.current.getBoundingClientRect();
    const width = Math.max(300, rect.width);

    // Responsive dynamic height: 360px on small screens, ~430px on 1080p, up to 540px on 2K/4K
    // Strictly ensuring total page height <= 2 * innerHeight
    const vhHeight = Math.round(window.innerHeight * 0.44);
    const height = Math.min(Math.max(360, vhHeight), 540);

    // Set backing store dimensions to physical device pixels for high-DPI rendering
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    // Scale drawing context so all coordinates are in CSS logical pixels
    ctx.scale(dpr, dpr);

    // Clear background
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, width, height);

    if (visibleBars.length === 0) {
      ctx.fillStyle = '#9C978E';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      const msg = isLoading
        ? '行情数据请求中...'
        : '暂无本地真实行情数据（请执行真实数据同步，或该标的/市场未通过验证）';
      ctx.fillText(msg, width / 2, height / 2 - 10);
      ctx.font = '11px sans-serif';
      ctx.fillStyle = '#B4AFA7';
      ctx.fillText('本系统严格遵循真实性准则，无数据时不展示合成演示K线', width / 2, height / 2 + 16);
      return;
    }

    // Adaptive vertical partitions based on dynamic height:
    // Main K-line area occupies ~63% of height
    const chartLeft = 12;
    const rightMargin = width >= 2560 ? 84 : 70;
    const chartRight = width - rightMargin;
    const chartWidth = chartRight - chartLeft;

    const kTop = 16;
    const kHeight = Math.round(height * 0.63);
    const kBottom = kTop + kHeight;

    const vTop = kBottom + 18;
    const vHeight = Math.max(60, height - vTop - 24);
    const vBottom = vTop + vHeight;

    // 1. Calculate price range for visible bars
    let minPrice = Infinity;
    let maxPrice = -Infinity;

    for (let i = 0; i < visibleBars.length; i++) {
      const b = visibleBars[i];
      if (b.low < minPrice) minPrice = b.low;
      if (b.high > maxPrice) maxPrice = b.high;

      if (mainOverlay === 'MA') {
        if (b.ma_5) { minPrice = Math.min(minPrice, b.ma_5); maxPrice = Math.max(maxPrice, b.ma_5); }
        if (b.ma_10) { minPrice = Math.min(minPrice, b.ma_10); maxPrice = Math.max(maxPrice, b.ma_10); }
        if (b.ma_20) { minPrice = Math.min(minPrice, b.ma_20); maxPrice = Math.max(maxPrice, b.ma_20); }
        if (b.ma_60) { minPrice = Math.min(minPrice, b.ma_60); maxPrice = Math.max(maxPrice, b.ma_60); }
      } else if (mainOverlay === 'EMA') {
        if (b.ema_12) { minPrice = Math.min(minPrice, b.ema_12); maxPrice = Math.max(maxPrice, b.ema_12); }
        if (b.ema_26) { minPrice = Math.min(minPrice, b.ema_26); maxPrice = Math.max(maxPrice, b.ema_26); }
      } else if (mainOverlay === 'BOLL') {
        if (b.boll_upper) maxPrice = Math.max(maxPrice, b.boll_upper);
        if (b.boll_lower) minPrice = Math.min(minPrice, b.boll_lower);
      }
    }

    const pricePadding = (maxPrice - minPrice) * 0.05 || 1;
    minPrice -= pricePadding;
    maxPrice += pricePadding;
    if (minPrice <= 0) minPrice = 0.01;

    const priceToY = (p: number) => kBottom - ((p - minPrice) / (maxPrice - minPrice)) * kHeight;

    // 2. Compute range for Sub-chart indicator
    let subMin = 0;
    let subMax = 1;

    if (subIndicator === 'VOL') {
      subMax = Math.max(...visibleBars.map((b) => b.volume), 10);
    } else if (subIndicator === 'MACD') {
      let maxVal = 0.01;
      for (const b of visibleBars) {
        if (b.macd_dif !== undefined && b.macd_dif !== null) maxVal = Math.max(maxVal, Math.abs(b.macd_dif));
        if (b.macd_dea !== undefined && b.macd_dea !== null) maxVal = Math.max(maxVal, Math.abs(b.macd_dea));
        if (b.macd_hist !== undefined && b.macd_hist !== null) maxVal = Math.max(maxVal, Math.abs(b.macd_hist));
      }
      subMin = -maxVal * 1.1;
      subMax = maxVal * 1.1;
    } else if (subIndicator === 'RSI' || subIndicator === 'KDJ') {
      subMin = 0;
      subMax = 100;
    } else if (subIndicator === 'ATR') {
      const atrs = visibleBars.map((b) => b.atr_14 || 0).filter((v) => v > 0);
      subMin = atrs.length > 0 ? Math.min(...atrs) * 0.9 : 0;
      subMax = atrs.length > 0 ? Math.max(...atrs) * 1.1 : 10;
    }

    const subToY = (val: number) => {
      const clamped = Math.min(Math.max(val, subMin), subMax);
      return vBottom - ((clamped - subMin) / (subMax - subMin || 1)) * vHeight;
    };

    const barSpacing = chartWidth / visibleBars.length;
    const candleWidth = Math.max(2, Math.min(20, barSpacing * 0.72));

    // 3. Draw Grids & Axes with Crisp 1px Lines
    ctx.strokeStyle = '#F0ECE1';
    ctx.lineWidth = 1;

    // Horizontal grid lines for K-line
    const priceSteps = height >= 480 ? 6 : 5;
    ctx.fillStyle = '#9C978E';
    ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
    ctx.textAlign = 'left';

    for (let i = 0; i <= priceSteps; i++) {
      const y = Math.floor(kTop + (kHeight / priceSteps) * i) + 0.5;
      const p = maxPrice - ((maxPrice - minPrice) / priceSteps) * i;
      ctx.beginPath();
      ctx.moveTo(chartLeft, y);
      ctx.lineTo(chartRight, y);
      ctx.stroke();

      ctx.fillText(p.toFixed(2), chartRight + 6, y + 3);
    }

    // Sub-chart grid lines
    ctx.beginPath();
    ctx.moveTo(chartLeft, Math.floor(vTop) + 0.5);
    ctx.lineTo(chartRight, Math.floor(vTop) + 0.5);
    ctx.moveTo(chartLeft, Math.floor(vBottom) + 0.5);
    ctx.lineTo(chartRight, Math.floor(vBottom) + 0.5);
    ctx.stroke();

    if (subIndicator === 'VOL') {
      ctx.fillText(subMax >= 10000 ? (subMax / 10000).toFixed(1) + '万' : subMax.toString(), chartRight + 6, vTop + 10);
      ctx.fillText('0', chartRight + 6, vBottom);
    } else if (subIndicator === 'MACD') {
      const yZero = Math.floor(subToY(0)) + 0.5;
      ctx.strokeStyle = '#D6D1C6';
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.moveTo(chartLeft, yZero);
      ctx.lineTo(chartRight, yZero);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillText(subMax.toFixed(2), chartRight + 6, vTop + 10);
      ctx.fillText(subMin.toFixed(2), chartRight + 6, vBottom);
    } else if (subIndicator === 'RSI' || subIndicator === 'KDJ') {
      // 80 & 20 reference lines
      const y80 = Math.floor(subToY(80)) + 0.5;
      const y20 = Math.floor(subToY(20)) + 0.5;
      ctx.strokeStyle = '#EAE6DF';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(chartLeft, y80);
      ctx.lineTo(chartRight, y80);
      ctx.moveTo(chartLeft, y20);
      ctx.lineTo(chartRight, y20);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillText('80', chartRight + 6, y80 + 3);
      ctx.fillText('20', chartRight + 6, y20 + 3);
    } else if (subIndicator === 'ATR') {
      ctx.fillText(subMax.toFixed(2), chartRight + 6, vTop + 10);
      ctx.fillText(subMin.toFixed(2), chartRight + 6, vBottom);
    }

    // 4. Render K-lines
    for (let i = 0; i < visibleBars.length; i++) {
      const b = visibleBars[i];
      const xCenter = chartLeft + i * barSpacing + barSpacing / 2;
      const isUp = b.close >= b.open;
      const barColor = isUp ? upColor : downColor;

      const yOpen = priceToY(b.open);
      const yClose = priceToY(b.close);
      const yHigh = priceToY(b.high);
      const yLow = priceToY(b.low);

      // Wick
      ctx.strokeStyle = barColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(Math.floor(xCenter) + 0.5, yHigh);
      ctx.lineTo(Math.floor(xCenter) + 0.5, yLow);
      ctx.stroke();

      // Body
      const bodyTop = Math.min(yOpen, yClose);
      const bodyHeight = Math.max(1.5, Math.abs(yClose - yOpen));
      ctx.fillStyle = barColor;
      ctx.fillRect(
        Math.floor(xCenter - candleWidth / 2),
        bodyTop,
        candleWidth,
        bodyHeight
      );
    }

    // 5. Render Main Overlay Indicators
    const drawOverlayLine = (key: keyof IndicatorRow, color: string) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      let started = false;

      for (let i = 0; i < visibleBars.length; i++) {
        const val = visibleBars[i][key] as number | undefined | null;
        if (val !== undefined && val !== null && !isNaN(val)) {
          const x = chartLeft + i * barSpacing + barSpacing / 2;
          const y = priceToY(val);
          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
      }
      ctx.stroke();
    };

    if (mainOverlay === 'MA') {
      drawOverlayLine('ma_5', '#0284C7');   // Sky blue
      drawOverlayLine('ma_10', '#E11D48');  // Rose
      drawOverlayLine('ma_20', '#D97706');  // Amber
      drawOverlayLine('ma_60', '#6B7280');  // Gray
    } else if (mainOverlay === 'EMA') {
      drawOverlayLine('ema_12', '#0284C7');
      drawOverlayLine('ema_26', '#E11D48');
    } else if (mainOverlay === 'BOLL') {
      drawOverlayLine('boll_upper', '#0284C7');
      drawOverlayLine('boll_mid', '#D97706');
      drawOverlayLine('boll_lower', '#0284C7');
    }

    // 6. Render Sub-chart Indicator
    if (subIndicator === 'VOL') {
      for (let i = 0; i < visibleBars.length; i++) {
        const b = visibleBars[i];
        const xCenter = chartLeft + i * barSpacing + barSpacing / 2;
        const isUp = b.close >= b.open;
        const barColor = isUp ? upColor : downColor;
        const yVol = subToY(b.volume);
        const vH = Math.max(1, vBottom - yVol);

        ctx.fillStyle = barColor;
        ctx.fillRect(Math.floor(xCenter - candleWidth / 2), yVol, candleWidth, vH);
      }
    } else if (subIndicator === 'MACD') {
      // Draw MACD Histograms
      for (let i = 0; i < visibleBars.length; i++) {
        const b = visibleBars[i];
        const hist = b.macd_hist ?? 0;
        const xCenter = chartLeft + i * barSpacing + barSpacing / 2;
        const isUp = hist >= 0;
        const barColor = isUp ? upColor : downColor;
        const yHist = subToY(hist);
        const yZero = subToY(0);

        ctx.fillStyle = barColor;
        const top = Math.min(yHist, yZero);
        const h = Math.max(1, Math.abs(yHist - yZero));
        ctx.fillRect(Math.floor(xCenter - candleWidth / 2), top, candleWidth, h);
      }
      // Draw DIF and DEA lines
      const drawSubLine = (key: keyof IndicatorRow, color: string) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.3;
        ctx.beginPath();
        let started = false;
        for (let i = 0; i < visibleBars.length; i++) {
          const val = visibleBars[i][key] as number | undefined | null;
          if (val !== undefined && val !== null && !isNaN(val)) {
            const x = chartLeft + i * barSpacing + barSpacing / 2;
            const y = subToY(val);
            if (!started) { ctx.moveTo(x, y); started = true; }
            else { ctx.lineTo(x, y); }
          }
        }
        ctx.stroke();
      };
      drawSubLine('macd_dif', '#0284C7');
      drawSubLine('macd_dea', '#D97706');
    } else if (subIndicator === 'RSI') {
      const drawSubLine = (key: keyof IndicatorRow, color: string) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.3;
        ctx.beginPath();
        let started = false;
        for (let i = 0; i < visibleBars.length; i++) {
          const val = visibleBars[i][key] as number | undefined | null;
          if (val !== undefined && val !== null && !isNaN(val)) {
            const x = chartLeft + i * barSpacing + barSpacing / 2;
            const y = subToY(val);
            if (!started) { ctx.moveTo(x, y); started = true; }
            else { ctx.lineTo(x, y); }
          }
        }
        ctx.stroke();
      };
      drawSubLine('rsi_6', '#0284C7');
      drawSubLine('rsi_12', '#D97706');
      drawSubLine('rsi_24', '#7C3AED');
    } else if (subIndicator === 'KDJ') {
      const drawSubLine = (key: keyof IndicatorRow, color: string) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.3;
        ctx.beginPath();
        let started = false;
        for (let i = 0; i < visibleBars.length; i++) {
          const val = visibleBars[i][key] as number | undefined | null;
          if (val !== undefined && val !== null && !isNaN(val)) {
            const x = chartLeft + i * barSpacing + barSpacing / 2;
            const y = subToY(val);
            if (!started) { ctx.moveTo(x, y); started = true; }
            else { ctx.lineTo(x, y); }
          }
        }
        ctx.stroke();
      };
      drawSubLine('kdj_k', '#0284C7');
      drawSubLine('kdj_d', '#D97706');
      drawSubLine('kdj_j', '#E11D48');
    } else if (subIndicator === 'ATR') {
      ctx.strokeStyle = '#2563EB';
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < visibleBars.length; i++) {
        const val = visibleBars[i].atr_14;
        if (val !== undefined && val !== null && !isNaN(val)) {
          const x = chartLeft + i * barSpacing + barSpacing / 2;
          const y = subToY(val);
          if (!started) { ctx.moveTo(x, y); started = true; }
          else { ctx.lineTo(x, y); }
        }
      }
      ctx.stroke();
    }

    // 7. Time Axis Labels (Evenly Spaced Adaptively)
    ctx.fillStyle = '#9C978E';
    ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
    ctx.textAlign = 'center';
    const targetDateCount = Math.min(16, Math.max(4, Math.floor(chartWidth / 140)));
    const dateStep = Math.max(1, Math.floor(visibleBars.length / targetDateCount));

    for (let i = 0; i < visibleBars.length; i += dateStep) {
      const b = visibleBars[i];
      const x = chartLeft + i * barSpacing + barSpacing / 2;
      const dateStr = b.ts ? b.ts.split('T')[0] : '';
      ctx.fillText(dateStr, x, height - 6);
    }

    // 8. Crosshair and Tooltip
    if (hoverIndex !== null && hoverIndex >= 0 && hoverIndex < visibleBars.length && mousePos) {
      const hBar = visibleBars[hoverIndex];
      const xCross = Math.floor(chartLeft + hoverIndex * barSpacing + barSpacing / 2) + 0.5;

      ctx.strokeStyle = '#4D4A45';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);

      // Vertical line across both charts
      ctx.beginPath();
      ctx.moveTo(xCross, kTop);
      ctx.lineTo(xCross, vBottom);
      ctx.stroke();

      // Horizontal line in active zone
      if (mousePos.y >= kTop && mousePos.y <= kBottom) {
        ctx.beginPath();
        ctx.moveTo(chartLeft, Math.floor(mousePos.y) + 0.5);
        ctx.lineTo(chartRight, Math.floor(mousePos.y) + 0.5);
        ctx.stroke();
      } else if (mousePos.y >= vTop && mousePos.y <= vBottom) {
        ctx.beginPath();
        ctx.moveTo(chartLeft, Math.floor(mousePos.y) + 0.5);
        ctx.lineTo(chartRight, Math.floor(mousePos.y) + 0.5);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // Floating Compact Tooltip Box (Top Right Overlay)
      const tooltipW = Math.min(190, Math.max(150, Math.floor(width * 0.14)));
      const tooltipH = 135;
      const tooltipX = chartRight - tooltipW - 8;
      const tooltipY = kTop + 8;

      ctx.fillStyle = 'rgba(255, 255, 255, 0.94)';
      ctx.strokeStyle = '#EAE6DF';
      ctx.lineWidth = 1;
      ctx.fillRect(tooltipX, tooltipY, tooltipW, tooltipH);
      ctx.strokeRect(tooltipX, tooltipY, tooltipW, tooltipH);

      const rowY = (r: number) => tooltipY + 16 + r * 17;

      ctx.textAlign = 'left';
      ctx.fillStyle = '#6E6B65';
      ctx.font = '10px sans-serif';
      ctx.fillText('时间:', tooltipX + 8, rowY(0));
      ctx.textAlign = 'right';
      ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
      ctx.fillStyle = '#1F1E1D';
      ctx.fillText(hBar.ts ? hBar.ts.split('T')[0] : '--', tooltipX + tooltipW - 8, rowY(0));

      ctx.textAlign = 'left';
      ctx.fillStyle = '#6E6B65';
      ctx.font = '10px sans-serif';
      ctx.fillText('开盘:', tooltipX + 8, rowY(1));
      ctx.textAlign = 'right';
      ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
      ctx.fillText(hBar.open.toFixed(2), tooltipX + tooltipW - 8, rowY(1));

      ctx.textAlign = 'left';
      ctx.fillStyle = '#6E6B65';
      ctx.font = '10px sans-serif';
      ctx.fillText('最高:', tooltipX + 8, rowY(2));
      ctx.textAlign = 'right';
      ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
      ctx.fillText(hBar.high.toFixed(2), tooltipX + tooltipW - 8, rowY(2));

      ctx.textAlign = 'left';
      ctx.fillStyle = '#6E6B65';
      ctx.font = '10px sans-serif';
      ctx.fillText('最低:', tooltipX + 8, rowY(3));
      ctx.textAlign = 'right';
      ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
      ctx.fillText(hBar.low.toFixed(2), tooltipX + tooltipW - 8, rowY(3));

      ctx.textAlign = 'left';
      ctx.fillStyle = '#6E6B65';
      ctx.font = '10px sans-serif';
      ctx.fillText('收盘:', tooltipX + 8, rowY(4));
      ctx.textAlign = 'right';
      ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
      const cColor = hBar.close >= hBar.open ? upColor : downColor;
      ctx.fillStyle = cColor;
      ctx.fillText(hBar.close.toFixed(2), tooltipX + tooltipW - 8, rowY(4));

      ctx.textAlign = 'left';
      ctx.fillStyle = '#6E6B65';
      ctx.font = '10px sans-serif';
      ctx.fillText('成交:', tooltipX + 8, rowY(5));
      ctx.textAlign = 'right';
      ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
      ctx.fillStyle = '#1F1E1D';
      ctx.fillText((hBar.volume / 10000).toFixed(1) + '万', tooltipX + tooltipW - 8, rowY(5));

      ctx.textAlign = 'left';
      ctx.fillStyle = '#6E6B65';
      ctx.font = '10px sans-serif';
      ctx.fillText(`${subIndicator}:`, tooltipX + 8, rowY(6));
      ctx.textAlign = 'right';
      ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
      ctx.fillStyle = '#1F1E1D';
      let subText = '--';
      if (subIndicator === 'VOL') subText = (hBar.volume / 10000).toFixed(1) + '万';
      else if (subIndicator === 'MACD') subText = `DIF:${hBar.macd_dif?.toFixed(2) || '--'} DEA:${hBar.macd_dea?.toFixed(2) || '--'}`;
      else if (subIndicator === 'RSI') subText = `R6:${hBar.rsi_6?.toFixed(1) || '--'} R14:${hBar.rsi_14?.toFixed(1) || '--'}`;
      else if (subIndicator === 'KDJ') subText = `K:${hBar.kdj_k?.toFixed(1) || '--'} D:${hBar.kdj_d?.toFixed(1) || '--'} J:${hBar.kdj_j?.toFixed(1) || '--'}`;
      else if (subIndicator === 'ATR') subText = `${hBar.atr_14?.toFixed(2) || '--'}`;
      ctx.fillText(subText, tooltipX + tooltipW - 8, rowY(6));
    }
  }, [
    visibleBars,
    mainOverlay,
    subIndicator,
    upColor,
    downColor,
    hoverIndex,
    mousePos,
    isLoading,
  ]);

  useEffect(() => {
    renderChart();
  }, [renderChart]);

  // Robust ResizeObserver with RequestAnimationFrame debouncing & DPR change detection
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let animFrameId: number;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(animFrameId);
      animFrameId = requestAnimationFrame(() => {
        renderChart();
      });
    });

    observer.observe(container);

    const handleResize = () => {
      cancelAnimationFrame(animFrameId);
      animFrameId = requestAnimationFrame(() => {
        renderChart();
      });
    };
    window.addEventListener('resize', handleResize);

    // Watch for display resolution / DPR changes (e.g. moving between screens)
    const mediaQuery = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
    const handleDprChange = () => renderChart();
    try {
      mediaQuery.addEventListener('change', handleDprChange);
    } catch {
      // Safari legacy fallback
      mediaQuery.addListener(handleDprChange);
    }

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animFrameId);
      try {
        mediaQuery.removeEventListener('change', handleDprChange);
      } catch {
        mediaQuery.removeListener(handleDprChange);
      }
    };
  }, [renderChart]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setMousePos({ x, y });

    const chartLeft = 12;
    const rightMargin = rect.width >= 2560 ? 84 : 70;
    const chartRight = rect.width - rightMargin;
    const chartWidth = chartRight - chartLeft;

    if (x >= chartLeft && x <= chartRight && visibleBars.length > 0) {
      const barSpacing = chartWidth / visibleBars.length;
      const idx = Math.floor((x - chartLeft) / barSpacing);
      setHoverIndex(Math.min(Math.max(0, idx), visibleBars.length - 1));
    } else {
      setHoverIndex(null);
    }

    if (isDragging) {
      const deltaX = e.clientX - dragStartX;
      const barSpacing = chartWidth / visibleBars.length;
      const shiftBars = Math.round(deltaX / barSpacing);
      setOffsetRight(Math.max(0, dragStartOffset + shiftBars));
    }
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    setIsDragging(true);
    setDragStartX(e.clientX);
    setDragStartOffset(offsetRight);
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    if (e.deltaY < 0) {
      setVisibleCount((c) => Math.max(20, c - 8));
    } else {
      setVisibleCount((c) => Math.min(bars.length, c + 8));
    }
  };

  const resetZoom = () => {
    setVisibleCount(90);
    setOffsetRight(0);
  };

  return (
    <div className="bg-white border-b border-warm-200" ref={containerRef}>
      {/* Top Toolbar: Timeframe, Adjustment, Main Overlay Selector, Sub-chart Tab, Color Switch */}
      <div className="px-3 sm:px-4 lg:px-6 py-1.5 border-b border-warm-100 flex flex-wrap items-center justify-between gap-y-1.5 gap-x-3 text-xs select-none">
        {/* Left: Timeframe, Adjustment, Overlay */}
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-[11px] text-warm-400 font-sans mr-0.5">周期:</span>
          {(['1d', '1w', '1M', '1Q', '1Y'] as Timeframe[]).map((tf) => (
            <button
              key={tf}
              onClick={() => onTimeframeChange(tf)}
              className={`px-2 py-0.5 rounded font-mono font-medium transition-colors ${
                timeframe === tf
                  ? 'bg-warm-800 text-white'
                  : 'text-warm-600 hover:bg-warm-100'
              }`}
            >
              {tf.toUpperCase()}
            </button>
          ))}

          <div className="h-3.5 w-px bg-warm-200 mx-1" />
          <span className="text-[11px] text-warm-400 font-sans mr-0.5">复权:</span>
          {[
            { id: 'none', label: '不复权' },
            { id: 'qfq', label: '前复权' },
            { id: 'hfq', label: '后复权' },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => onAdjTypeChange(item.id as AdjustType)}
              className={`px-1.5 py-0.5 rounded font-sans transition-colors ${
                adjType === item.id
                  ? 'bg-warm-700 text-white font-medium'
                  : 'text-warm-600 hover:bg-warm-100'
              }`}
            >
              {item.label}
            </button>
          ))}

          <div className="h-3.5 w-px bg-warm-200 mx-1" />
          {/* Main Overlay Selector */}
          <span className="text-[11px] text-warm-400 font-sans mr-0.5">主图:</span>
          {(['MA', 'EMA', 'BOLL', 'NONE'] as const).map((ov) => (
            <button
              key={ov}
              onClick={() => setMainOverlay(ov)}
              className={`px-1.5 py-0.5 rounded font-mono font-medium transition-colors ${
                mainOverlay === ov
                  ? 'bg-warm-200 text-warm-900 border border-warm-300'
                  : 'text-warm-500 hover:bg-warm-100'
              }`}
            >
              {ov}
            </button>
          ))}
        </div>

        {/* Right: Sub-chart Indicator Tabs & Controls */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Sub-chart Tabs (Strictly Tabbed to Prevent Vertical Stack Overflow) */}
          <div className="flex items-center gap-0.5 bg-warm-50 p-0.5 rounded border border-warm-200 text-[11px] font-mono">
            <span className="text-[10px] text-warm-400 px-1 font-sans">副图:</span>
            {(['VOL', 'MACD', 'RSI', 'KDJ', 'ATR'] as SubChartIndicator[]).map((ind) => (
              <button
                key={ind}
                onClick={() => setSubIndicator(ind)}
                className={`px-1.5 py-0.5 rounded font-medium transition-colors ${
                  subIndicator === ind
                    ? 'bg-white text-warm-900 shadow-xs border border-warm-200 font-semibold'
                    : 'text-warm-500 hover:text-warm-800'
                }`}
              >
                {ind}
              </button>
            ))}
          </div>

          <div className="h-3.5 w-px bg-warm-200" />

          {/* Color Scheme Switch */}
          <button
            onClick={() => onColorSchemeChange(colorScheme === 'CN' ? 'INTL' : 'CN')}
            className="px-2 py-0.5 rounded border border-warm-200 text-warm-700 hover:bg-warm-50 text-[11px] flex items-center gap-1"
            title="切换涨跌配色模式"
          >
            <span>配色:</span>
            <span className="font-semibold text-warm-900">
              {colorScheme === 'CN' ? '中国红/绿' : '国际绿/红'}
            </span>
          </button>

          {/* Zoom Controls */}
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => setVisibleCount((c) => Math.max(20, c - 15))}
              className="p-1 rounded hover:bg-warm-100 text-warm-600"
              title="放大 (查看更少K线)"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setVisibleCount((c) => Math.min(bars.length, c + 15))}
              className="p-1 rounded hover:bg-warm-100 text-warm-600"
              title="缩小 (查看更多K线)"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={resetZoom}
              className="p-1 rounded hover:bg-warm-100 text-warm-600"
              title="复位视图"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Chart Canvas Area (Dynamic responsive height, clean backing store) */}
      <div className="relative w-full cursor-crosshair select-none bg-white">
        <canvas
          ref={canvasRef}
          onMouseMove={handleMouseMove}
          onMouseDown={handleMouseDown}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => {
            setHoverIndex(null);
            setIsDragging(false);
          }}
          onWheel={handleWheel}
          className="block w-full"
        />
      </div>
    </div>
  );
};
