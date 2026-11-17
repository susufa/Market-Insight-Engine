import React, { useEffect, useMemo, useRef, useState } from 'react';
import { X, Download, Layers, CalendarClock, TriangleAlert, RefreshCw } from 'lucide-react';
import { createAcquisitionTask } from '../api';
import { useModalBehavior } from '../hooks/useDisplay';

interface DataUpdateDialogProps {
  isOpen: boolean;
  onClose: () => void;
  currentSymbol: string;
  onTaskCreated: (taskId: string) => void;
}

type Mode = 'current' | 'batch';
type Range = '1m' | '1y' | '3y' | 'all';

const RANGES: Array<{ id: Range; label: string; hint: string }> = [
  { id: '1m', label: '近 1 月', hint: '增量校验' },
  { id: '1y', label: '近 1 年', hint: '默认' },
  { id: '3y', label: '近 3 年', hint: '回测样本' },
  { id: 'all', label: '全量历史', hint: '2015 起' },
];

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

export const DataUpdateDialog: React.FC<DataUpdateDialogProps> = ({
  isOpen,
  onClose,
  currentSymbol,
  onTaskCreated,
}) => {
  const [mode, setMode] = useState<Mode>('current');
  const [batch, setBatch] = useState('600519.SH, 000858.SZ, 300750.SZ, 601318.SH');
  const [range, setRange] = useState<Range>('1y');
  const [provider, setProvider] = useState<'auto' | 'akshare'>('auto');
  const [force, setForce] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const firstBtn = useRef<HTMLButtonElement | null>(null);

  useModalBehavior(isOpen, onClose);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setSubmitting(false);
    const timer = window.setTimeout(() => firstBtn.current?.focus(), 30);
    return () => window.clearTimeout(timer);
  }, [isOpen]);

  const symbols = useMemo(() => {
    if (mode === 'current') return [currentSymbol];
    return Array.from(
      new Set(
        batch
          .split(/[,;\s\n]+/)
          .map((s) => s.trim().toUpperCase())
          .filter((s) => s.length > 0),
      ),
    );
  }, [mode, batch, currentSymbol]);

  const window_ = useMemo(() => {
    const end = new Date();
    const start = new Date(end);
    if (range === '1m') start.setMonth(start.getMonth() - 1);
    else if (range === '1y') start.setFullYear(start.getFullYear() - 1);
    else if (range === '3y') start.setFullYear(start.getFullYear() - 3);
    else start.setFullYear(2015, 0, 1);
    return { start: isoDate(start), end: isoDate(end) };
  }, [range]);

  if (!isOpen) return null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (symbols.length === 0) {
      setError('请输入至少一个有效的标的代码');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await createAcquisitionTask({
        symbols,
        timeframe: '1d',
        start_date: window_.start,
        end_date: window_.end,
        provider_preference: provider,
        force_refresh: force,
      });
      onTaskCreated(res.task_id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建数据更新任务失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="scrim"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <form
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-title"
        onSubmit={submit}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="dialog__head">
          <div className="flex flex-col gap-1">
            <span className="eyebrow">ACQUISITION · 数据获取编排</span>
            <h2 id="update-title" className="display text-[1.05rem] text-warm-900">
              更新行情数据
            </h2>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="关闭">
            <X size={14} />
          </button>
        </div>

        <div className="dialog__body">
          {error && (
            <div className="note note--warn">
              <TriangleAlert size={12} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="field">
            <span className="eyebrow">更新范围</span>
            <div className="grid grid-cols-2 gap-1">
              <button
                type="button"
                ref={mode === 'current' ? firstBtn : undefined}
                className="mode-chip"
                data-active={mode === 'current'}
                onClick={() => setMode('current')}
              >
                <Download size={12} />
                当前标的
                <span className="mode-chip__tag">{currentSymbol}</span>
              </button>
              <button
                type="button"
                className="mode-chip"
                data-active={mode === 'batch'}
                onClick={() => setMode('batch')}
              >
                <Layers size={12} />
                批量标的池
                <span className="mode-chip__tag">{symbols.length} 个</span>
              </button>
            </div>
          </div>

          {mode === 'batch' && (
            <div className="field">
              <span className="eyebrow">标的代码 · 逗号 / 空格 / 换行分隔</span>
              <textarea
                className="textarea"
                rows={3}
                spellCheck={false}
                value={batch}
                onChange={(event) => setBatch(event.target.value)}
                placeholder="600519.SH, 000858.SZ, 300750.SZ"
              />
            </div>
          )}

          <div className="field">
            <span className="eyebrow flex items-center gap-1">
              <CalendarClock size={11} />
              时间跨度
            </span>
            <div className="grid grid-cols-4 gap-1">
              {RANGES.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className="range-chip"
                  data-active={range === item.id}
                  onClick={() => setRange(item.id)}
                >
                  <span>{item.label}</span>
                  <span className="range-chip__hint">{item.hint}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div className="field">
              <span className="eyebrow">数据通道</span>
              <select
                className="select"
                value={provider}
                onChange={(event) => setProvider(event.target.value as 'auto' | 'akshare')}
              >
                <option value="auto">自动故障降级（Auto）</option>
                <option value="akshare">AKShare 官方通道</option>
              </select>
            </div>
            <div className="field">
              <span className="eyebrow">写入策略</span>
              <label className="flex h-[1.9rem] cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  className="checkbox"
                  checked={force}
                  onChange={(event) => setForce(event.target.checked)}
                />
                <span className="text-[0.72rem] text-warm-600">强制覆盖本地存储</span>
              </label>
            </div>
          </div>

          <div className="note note--info">
            <span className="font-mono">
              将写入 {symbols.length} 个标的 · {window_.start} → {window_.end} · 1D ·{' '}
              {provider === 'auto' ? '自动降级' : 'AKShare'}
              {force ? ' · 强制覆盖' : ' · 增量合并'}
            </span>
          </div>
        </div>

        <div className="dialog__foot">
          <button type="button" className="btn btn--quiet" onClick={onClose} disabled={submitting}>
            取消
          </button>
          <button type="submit" className="btn btn--primary" disabled={submitting}>
            {submitting ? <RefreshCw size={12} className="spin" /> : <Download size={12} />}
            {submitting ? '正在创建任务…' : '开始更新行情'}
          </button>
        </div>
      </form>
    </div>
  );
};
