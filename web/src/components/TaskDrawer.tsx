import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  X,
  RefreshCw,
  Play,
  Square,
  Activity,
  CheckCircle2,
  TriangleAlert,
  XCircle,
  Clock,
  Trash2,
} from 'lucide-react';
import {
  cancelAcquisitionTask,
  cleanupZombieTasks,
  fetchAcquisitionTask,
  listAcquisitionTasks,
  resumeAcquisitionTask,
} from '../api';
import type { AcquisitionTaskRecord } from '../types';
import { useModalBehavior } from '../hooks/useDisplay';
import { fmtClock } from '../lib/format';

interface TaskDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  activeTaskId: string | null;
  onSelectTaskId: (taskId: string) => void;
  onTaskCompleted: () => void;
}

const ACTIVE_STATES = ['PENDING', 'RUNNING'];

function StatusChip({ status }: { status: string }) {
  if (status === 'SUCCESS') {
    return (
      <span className="chip chip--ok">
        <CheckCircle2 size={10} /> SUCCESS
      </span>
    );
  }
  if (status === 'RUNNING') {
    return (
      <span className="chip chip--warn">
        <RefreshCw size={10} className="spin" /> RUNNING
      </span>
    );
  }
  if (status === 'PARTIAL_SUCCESS') {
    return (
      <span className="chip chip--warn">
        <TriangleAlert size={10} /> PARTIAL
      </span>
    );
  }
  if (status === 'FAILED' || status === 'INTERRUPTED') {
    return (
      <span className="chip chip--danger">
        <XCircle size={10} /> {status}
      </span>
    );
  }
  if (status === 'CANCELLED') {
    return (
      <span className="chip">
        <Square size={9} /> CANCELLED
      </span>
    );
  }
  return (
    <span className="chip">
      <Clock size={10} /> {status}
    </span>
  );
}

export const TaskDrawer: React.FC<TaskDrawerProps> = ({
  isOpen,
  onClose,
  activeTaskId,
  onSelectTaskId,
  onTaskCompleted,
}) => {
  const [task, setTask] = useState<AcquisitionTaskRecord | null>(null);
  const [recent, setRecent] = useState<AcquisitionTaskRecord[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const completedRef = useRef<string | null>(null);

  useModalBehavior(isOpen, onClose);

  const loadRecent = useCallback(async () => {
    setLoadingRecent(true);
    try {
      const res = await listAcquisitionTasks(12);
      setRecent(res.tasks ?? []);
    } catch {
      setRecent([]);
    } finally {
      setLoadingRecent(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    void loadRecent();
  }, [isOpen, loadRecent]);

  // Poll the selected task until it reaches a terminal state.
  useEffect(() => {
    if (!isOpen || !activeTaskId) {
      setTask(null);
      return;
    }
    let cancelled = false;
    let timer = 0;

    const tick = async () => {
      try {
        const data = await fetchAcquisitionTask(activeTaskId);
        if (cancelled) return;
        setTask(data);
        if (data.status === 'SUCCESS' && completedRef.current !== data.task_id) {
          completedRef.current = data.task_id;
          onTaskCompleted();
          void loadRecent();
        }
        if (ACTIVE_STATES.includes(data.status)) {
          timer = window.setTimeout(tick, 2000);
        } else {
          void loadRecent();
        }
      } catch {
        if (!cancelled) timer = window.setTimeout(tick, 4000);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [isOpen, activeTaskId, onTaskCompleted, loadRecent]);

  if (!isOpen) return null;

  const act = async (fn: () => Promise<unknown>, okText: string, failText: string) => {
    try {
      await fn();
      setMessage(okText);
      if (activeTaskId) setTask(await fetchAcquisitionTask(activeTaskId));
      void loadRecent();
    } catch (err) {
      setMessage(failText + ': ' + (err instanceof Error ? err.message : '未知错误'));
    }
  };

  const progress = task
    ? task.progress_percent ??
      (task.total_symbols > 0 ? (task.completed_symbols / task.total_symbols) * 100 : 0)
    : 0;
  const clampedProgress = Math.max(0, Math.min(100, progress));
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const isRunning = task !== null && ACTIVE_STATES.includes(task.status);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="行情采集任务监视器">
        <div className="drawer__head">
          <div className="flex items-center gap-2">
            <Activity size={14} className="text-warm-600" />
            <div className="flex flex-col">
              <span className="eyebrow">ORCHESTRATION · 任务编排</span>
              <span className="text-[0.85rem] font-semibold text-warm-900">采集任务监视器</span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() =>
                act(cleanupZombieTasks, '僵尸任务巡检完成', '巡检失败')
              }
              title="清理失联超过 120 秒的任务"
            >
              <Trash2 size={11} />
              巡检
            </button>
            <button type="button" className="icon-btn" onClick={onClose} aria-label="关闭">
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="drawer__body">
          {message && (
            <div className="note note--info">
              <span className="flex-1">{message}</span>
              <button
                type="button"
                className="text-warm-400"
                onClick={() => setMessage(null)}
                aria-label="关闭提示"
              >
                <X size={11} />
              </button>
            </div>
          )}

          {task ? (
            <div className="task-card">
              <div className="task-card__head">
                <div className="flex min-w-0 flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span className="num text-[0.74rem] font-semibold text-warm-900">
                      {task.task_id}
                    </span>
                    <StatusChip status={task.status} />
                  </div>
                  <span className="eyebrow">
                    {task.timeframe} · {task.start_date} → {task.end_date} · 创建 {fmtClock(task.created_at)}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {task.status === 'RUNNING' && (
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() =>
                        act(
                          () => cancelAcquisitionTask(task.task_id),
                          '已发送终止请求',
                          '终止失败',
                        )
                      }
                    >
                      <Square size={10} />
                      终止
                    </button>
                  )}
                  {(task.status === 'INTERRUPTED' ||
                    task.status === 'PARTIAL_SUCCESS' ||
                    task.status === 'FAILED') && (
                    <button
                      type="button"
                      className="btn btn--primary"
                      onClick={() =>
                        act(
                          () => resumeAcquisitionTask(task.task_id),
                          '已从断点恢复执行',
                          '恢复失败',
                        )
                      }
                    >
                      <Play size={10} />
                      断点续传
                    </button>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3 px-3 py-3">
                <div className="relative shrink-0">
                  <svg className="ring" width="64" height="64" viewBox="0 0 64 64">
                    <circle
                      className="ring__track"
                      cx="32"
                      cy="32"
                      r={radius}
                      fill="none"
                      strokeWidth="5"
                    />
                    <circle
                      className="ring__value"
                      cx="32"
                      cy="32"
                      r={radius}
                      fill="none"
                      strokeWidth="5"
                      strokeLinecap="round"
                      stroke={task.status === 'FAILED' ? '#DC2626' : task.status === 'SUCCESS' ? '#16A34A' : '#1F1E1D'}
                      strokeDasharray={circumference}
                      strokeDashoffset={circumference * (1 - clampedProgress / 100)}
                    />
                  </svg>
                  <span className="absolute inset-0 grid place-items-center num text-[0.74rem] font-semibold text-warm-900">
                    {clampedProgress.toFixed(0)}%
                  </span>
                </div>

                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="flex items-baseline justify-between">
                    <span className="eyebrow">执行进度</span>
                    <span className="num text-[0.72rem] text-warm-700">
                      {task.completed_symbols} / {task.total_symbols} 标的
                    </span>
                  </div>
                  <div className="ratio-bar" style={{ height: '0.3rem' }}>
                    <div
                      className="h-full"
                      style={{
                        width: clampedProgress + '%',
                        background:
                          task.status === 'FAILED'
                            ? '#DC2626'
                            : task.status === 'SUCCESS'
                              ? '#16A34A'
                              : '#1F1E1D',
                        transition: 'width .4s cubic-bezier(.2,.7,.2,1)',
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-[0.62rem] num text-warm-400">
                    <span className="flex items-center gap-1">
                      <span className={'led ' + (isRunning ? 'led--live' : 'led--off')} />
                      心跳 {fmtClock(task.last_heartbeat_at)}
                    </span>
                    <span>失败 {task.failed_symbols}</span>
                  </div>
                </div>
              </div>

              {task.error_message && (
                <div className="note note--warn mx-3 mb-3">
                  <TriangleAlert size={11} className="mt-0.5 shrink-0" />
                  <span>{task.error_message}</span>
                </div>
              )}

              {task.items && task.items.length > 0 && (
                <div className="border-t border-warm-200">
                  <div className="flex items-center justify-between px-3 py-1.5">
                    <span className="eyebrow">标的执行明细</span>
                    <span className="eyebrow">{task.items.length}</span>
                  </div>
                  <div className="max-h-56 overflow-y-auto">
                    {task.items.map((item) => (
                      <div className="task-item" key={item.item_id}>
                        <span className="flex items-center gap-2">
                          <span className="num text-[0.72rem] font-semibold text-warm-900">
                            {item.symbol}
                          </span>
                          {item.row_count > 0 && (
                            <span className="num text-[0.6rem] text-warm-400">
                              {item.row_count} 行
                            </span>
                          )}
                        </span>
                        <span className="flex items-center gap-2">
                          {item.execution_latency_ms != null && (
                            <span className="num text-[0.6rem] text-warm-400">
                              {item.execution_latency_ms.toFixed(0)}ms
                            </span>
                          )}
                          <StatusChip status={item.status} />
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="panel-empty">
              <span className="text-[0.74rem] font-medium text-warm-600">暂无选中的采集任务</span>
              <span className="text-[0.66rem] text-warm-400">
                点击下方历史任务可切换监视目标，或在「更新行情」中创建新任务。
              </span>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="eyebrow">HISTORY · 历史与近期任务</span>
              {loadingRecent && <RefreshCw size={11} className="spin text-warm-400" />}
            </div>
            <div className="task-card">
              {recent.length === 0 ? (
                <div className="px-3 py-4 text-center text-[0.7rem] text-warm-400">
                  暂无任务记录
                </div>
              ) : (
                recent.map((item) => (
                  <button
                    type="button"
                    key={item.task_id}
                    className="task-item w-full text-left"
                    style={
                      item.task_id === activeTaskId
                        ? { background: '#F7F5EF' }
                        : undefined
                    }
                    onClick={() => onSelectTaskId(item.task_id)}
                  >
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="flex items-center gap-1.5">
                        <span className="num text-[0.7rem] font-semibold text-warm-900">
                          {item.task_id.slice(0, 14)}
                        </span>
                        <StatusChip status={item.status} />
                      </span>
                      <span className="eyebrow">
                        {item.symbols.slice(0, 3).join(' · ')}
                        {item.symbols.length > 3 ? ' +' + (item.symbols.length - 3) : ''}
                      </span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-0.5">
                      <span className="num text-[0.66rem] text-warm-600">
                        {item.completed_symbols}/{item.total_symbols}
                      </span>
                      <span className="eyebrow">{fmtClock(item.created_at)}</span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="note">
            <span>
              任务状态由 SQLite WAL 事务表持久化，前端每 2 秒轮询一次；进程崩溃后可在重启后断点续传。
            </span>
          </div>
        </div>
      </aside>
    </>
  );
};
