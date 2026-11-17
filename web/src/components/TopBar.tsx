import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, RefreshCw, ArrowUpRight } from 'lucide-react';
import type { HealthState, IndexQuote, Security } from '../types';
import { fmtPct, fmtPrice, tone } from '../lib/format';

interface TopBarProps {
  indices: IndexQuote[];
  securities: Security[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  health: HealthState;
  isRefreshing: boolean;
  onRefresh: () => void;
}

const isMac =
  typeof navigator !== 'undefined' && /mac/i.test(navigator.platform || navigator.userAgent);

const HEALTH_COPY: Record<HealthState, { text: string; led: string; title: string }> = {
  live: { text: 'API ONLINE', led: 'led led--live', title: '本地 FastAPI 网关健康检查通过' },
  checking: { text: 'CHECKING', led: 'led led--warn', title: '正在探测本地 API 网关' },
  offline: { text: 'OFFLINE', led: 'led led--off', title: '未连接本地 API（127.0.0.1:8000）' },
};

export const TopBar: React.FC<TopBarProps> = ({
  indices,
  securities,
  selectedSymbol,
  onSelectSymbol,
  health,
  isRefreshing,
  onRefresh,
}) => {
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const results = useMemo(() => {
    const keyword = term.trim().toLowerCase();
    const pool = keyword
      ? securities.filter(
          (s) =>
            s.symbol.toLowerCase().includes(keyword) ||
            s.name.toLowerCase().includes(keyword),
        )
      : securities;
    return pool.slice(0, 40);
  }, [securities, term]);

  useEffect(() => {
    setActive(0);
  }, [term, open]);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
      if ((event.key === 'k' || event.key === 'K') && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      } else if (event.key === '/' && !typing) {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener('pointerdown', onPointerDown, true);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('pointerdown', onPointerDown, true);
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  const choose = useCallback(
    (symbol: string) => {
      onSelectSymbol(symbol);
      setTerm('');
      setOpen(false);
      inputRef.current?.blur();
    },
    [onSelectSymbol],
  );

  const onInputKey = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, Math.max(0, results.length - 1)));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Enter') {
      const hit = results[active];
      if (hit) choose(hit.symbol);
    } else if (event.key === 'Escape') {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  return (
    <header className="topbar">
      <div className="shell-bleed topbar__inner">
        <div className="brand">
          <div className="brand__mark">MIE</div>
          <div>
            <div className="brand__name">Market Insight Engine</div>
            <div className="brand__sub">本地优先 · 行情终端 beta 0.1.0</div>
          </div>
        </div>

        <div className="index-strip" aria-label="指数快照">
          {indices.map((item) => (
            <div
              className="index-cell"
              key={item.symbol}
              title={item.label + ' ' + item.symbol}
            >
              <span className="index-cell__name">{item.label}</span>
              <span className="index-cell__px">{fmtPrice(item.price)}</span>
              <span className={'index-cell__pct ' + tone(item.pct)}>
                {item.price === null ? '未收录' : fmtPct(item.pct)}
              </span>
            </div>
          ))}
        </div>

        <div className="topbar__actions">
          <div className="search" ref={wrapRef}>
            <div className="search__box">
              <Search size={13} strokeWidth={1.8} className="shrink-0 text-warm-400" />
              <input
                ref={inputRef}
                className="search__input"
                placeholder="搜索代码 / 名称"
                value={term}
                spellCheck={false}
                autoComplete="off"
                aria-label="搜索标的"
                onChange={(event) => {
                  setTerm(event.target.value);
                  setOpen(true);
                }}
                onFocus={() => setOpen(true)}
                onKeyDown={onInputKey}
              />
              <span className="search__kbd" title="按 Ctrl/⌘ + K 快速聚焦">
                {isMac ? '⌘K' : 'Ctrl K'}
              </span>
            </div>

            {open && (
              <div className="search__pop" role="listbox" aria-label="标的搜索结果">
                <div className="search__meta">
                  <span className="eyebrow">{term.trim() ? 'SEARCH' : 'RECENT'}</span>
                  <span className="eyebrow">
                    {results.length} / {securities.length} 标的
                  </span>
                </div>
                <div className="search__list">
                  {results.length === 0 ? (
                    <div className="px-2 py-3 text-center text-[0.7rem] text-warm-400">
                      {securities.length === 0
                        ? '本地标的名录为空 · 请先执行「更新行情」'
                        : '未找到匹配标的'}
                    </div>
                  ) : (
                    results.map((item, index) => (
                      <button
                        type="button"
                        key={item.symbol}
                        role="option"
                        aria-selected={item.symbol === selectedSymbol}
                        className="search__item"
                        data-active={index === active}
                        data-selected={item.symbol === selectedSymbol}
                        onMouseEnter={() => setActive(index)}
                        onClick={() => choose(item.symbol)}
                      >
                        <span className="flex min-w-0 items-baseline gap-2">
                          <span className="search__item-symbol">{item.symbol}</span>
                          <span className="search__item-name truncate">{item.name}</span>
                        </span>
                        <span className="flex shrink-0 items-center gap-1.5">
                          <span className="eyebrow">{item.market}</span>
                          {index === active && (
                            <ArrowUpRight size={11} className="text-warm-400" />
                          )}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="chip chip--quiet" title={HEALTH_COPY[health].title}>
            <span className={HEALTH_COPY[health].led} />
            <span>{HEALTH_COPY[health].text}</span>
          </div>

          <button
            type="button"
            className="btn btn--ghost"
            onClick={onRefresh}
            disabled={isRefreshing}
            title="重新拉取报价、指标与预测"
            aria-label="刷新全部数据"
          >
            <RefreshCw size={12} className={isRefreshing ? 'spin' : undefined} />
            <span className="hidden lg:inline">刷新</span>
          </button>
        </div>
      </div>
    </header>
  );
};
