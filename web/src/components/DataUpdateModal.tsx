import React, { useState } from 'react';
import { X, RefreshCw, Layers, Calendar, AlertCircle } from 'lucide-react';
import { createAcquisitionTask } from '../api';

interface DataUpdateModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentSymbol: string;
  onTaskCreated: (taskId: string) => void;
}

export const DataUpdateModal: React.FC<DataUpdateModalProps> = ({
  isOpen,
  onClose,
  currentSymbol,
  onTaskCreated,
}) => {
  const [updateMode, setUpdateMode] = useState<'current' | 'batch'>('current');
  const [batchSymbols, setBatchSymbols] = useState('600519.SH, 000858.SZ, 300750.SZ, 601318.SH');
  const [dateRange, setDateRange] = useState<'1m' | '1y' | '3y' | 'all'>('1y');
  const [provider, setProvider] = useState<'auto' | 'akshare'>('auto');
  const [forceRefresh, setForceRefresh] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    let symbolsToUpdate: string[] = [];
    if (updateMode === 'current') {
      symbolsToUpdate = [currentSymbol];
    } else {
      symbolsToUpdate = batchSymbols
        .split(/[,;\s\n]+/)
        .map((s) => s.trim().toUpperCase())
        .filter((s) => s.length > 0);
    }

    if (symbolsToUpdate.length === 0) {
      setError('请输入至少一个有效的股票代码');
      setIsSubmitting(false);
      return;
    }

    // Calculate dates
    const now = new Date();
    let startDate: string | undefined;
    const endDate = now.toISOString().split('T')[0];

    if (dateRange === '1m') {
      const d = new Date(now);
      d.setMonth(d.getMonth() - 1);
      startDate = d.toISOString().split('T')[0];
    } else if (dateRange === '1y') {
      const d = new Date(now);
      d.setFullYear(d.getFullYear() - 1);
      startDate = d.toISOString().split('T')[0];
    } else if (dateRange === '3y') {
      const d = new Date(now);
      d.setFullYear(d.getFullYear() - 3);
      startDate = d.toISOString().split('T')[0];
    } else {
      startDate = '2015-01-01';
    }

    try {
      const res = await createAcquisitionTask({
        symbols: symbolsToUpdate,
        timeframe: '1d',
        start_date: startDate,
        end_date: endDate,
        provider_preference: provider,
        force_refresh: forceRefresh,
      });

      onTaskCreated(res.task_id);
      onClose();
    } catch (err: any) {
      setError(err?.message || '创建数据更新任务失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
      <div className="bg-white rounded-xl shadow-xl border border-warm-200 w-full max-w-lg overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-warm-200 bg-warm-50/50">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-warm-700" />
            <h3 className="font-semibold text-warm-900 text-sm">主动获取与更新行情数据</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-warm-400 hover:text-warm-700 hover:bg-warm-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-50 text-red-700 text-xs rounded-lg border border-red-200">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Mode Tabs */}
          <div>
            <label className="block text-xs font-medium text-warm-700 mb-1.5">更新范围</label>
            <div className="grid grid-cols-2 gap-2 p-1 bg-warm-100 rounded-lg text-xs font-medium">
              <button
                type="button"
                onClick={() => setUpdateMode('current')}
                className={`py-1.5 rounded-md transition-all flex items-center justify-center gap-1.5 ${
                  updateMode === 'current'
                    ? 'bg-white text-warm-900 shadow-xs'
                    : 'text-warm-600 hover:text-warm-900'
                }`}
              >
                <span>当前标的</span>
                <span className="font-mono text-[11px] text-warm-500">({currentSymbol})</span>
              </button>
              <button
                type="button"
                onClick={() => setUpdateMode('batch')}
                className={`py-1.5 rounded-md transition-all flex items-center justify-center gap-1.5 ${
                  updateMode === 'batch'
                    ? 'bg-white text-warm-900 shadow-xs'
                    : 'text-warm-600 hover:text-warm-900'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                <span>批量标的池</span>
              </button>
            </div>
          </div>

          {/* Batch Input */}
          {updateMode === 'batch' && (
            <div>
              <label className="block text-xs font-medium text-warm-700 mb-1">
                标的代码列表 (支持逗号、空格或换行分隔)
              </label>
              <textarea
                value={batchSymbols}
                onChange={(e) => setBatchSymbols(e.target.value)}
                rows={3}
                className="w-full text-xs font-mono p-2.5 rounded-lg border border-warm-200 focus:outline-none focus:ring-1 focus:ring-warm-500 bg-warm-50/50"
                placeholder="600519.SH, 000858.SZ, 300750.SZ"
              />
            </div>
          )}

          {/* Date Range Selection */}
          <div>
            <label className="block text-xs font-medium text-warm-700 mb-1.5 flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5 text-warm-500" />
              <span>时间跨度</span>
            </label>
            <div className="grid grid-cols-4 gap-2 text-xs font-medium">
              {[
                { key: '1m', label: '近1个月' },
                { key: '1y', label: '近1年' },
                { key: '3y', label: '近3年' },
                { key: 'all', label: '全量历史' },
              ].map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => setDateRange(opt.key as any)}
                  className={`py-1.5 rounded-lg border transition-all ${
                    dateRange === opt.key
                      ? 'border-warm-800 bg-warm-800 text-white shadow-xs'
                      : 'border-warm-200 bg-white text-warm-700 hover:bg-warm-50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Advanced Options */}
          <div className="pt-2 border-t border-warm-100 flex items-center justify-between text-xs text-warm-600">
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={forceRefresh}
                  onChange={(e) => setForceRefresh(e.target.checked)}
                  className="rounded border-warm-300 text-warm-800 focus:ring-warm-500"
                />
                <span>强制覆盖本地存储</span>
              </label>
            </div>
            <div className="flex items-center gap-1.5">
              <span>通道:</span>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value as any)}
                className="text-xs bg-warm-50 border border-warm-200 rounded px-1.5 py-0.5"
              >
                <option value="auto">自动故障降级 (Auto)</option>
                <option value="akshare">AKShare 官方通道</option>
              </select>
            </div>
          </div>

          {/* Actions */}
          <div className="pt-3 border-t border-warm-200 flex items-center justify-end gap-2.5">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-3.5 py-1.5 text-xs font-medium text-warm-700 hover:bg-warm-100 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 text-xs font-medium bg-warm-800 hover:bg-warm-900 text-white rounded-lg shadow-xs flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              {isSubmitting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              <span>{isSubmitting ? '启动任务中...' : '开始更新行情'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
