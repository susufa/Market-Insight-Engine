import React, { useEffect, useState } from 'react';
import {
  X,
  RefreshCw,
  Play,
  Square,
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Trash2,
} from 'lucide-react';
import {
  fetchAcquisitionTask,
  cancelAcquisitionTask,
  resumeAcquisitionTask,
  cleanupZombieTasks,
  listAcquisitionTasks,
} from '../api';
import { AcquisitionTaskRecord } from '../types';

interface TaskMonitorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  activeTaskId: string | null;
  onSelectTaskId: (taskId: string) => void;
  onTaskCompleted?: () => void;
}

export const TaskMonitorDrawer: React.FC<TaskMonitorDrawerProps> = ({
  isOpen,
  onClose,
  activeTaskId,
  onSelectTaskId,
  onTaskCompleted,
}) => {
  const [task, setTask] = useState<AcquisitionTaskRecord | null>(null);
  const [recentTasks, setRecentTasks] = useState<AcquisitionTaskRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Poll active task
  useEffect(() => {
    if (!isOpen || !activeTaskId) return;

    let isMounted = true;
    const fetchStatus = async () => {
      try {
        const data = await fetchAcquisitionTask(activeTaskId);
        if (isMounted) {
          setTask(data);
          if (data.status === 'SUCCESS' && onTaskCompleted) {
            onTaskCompleted();
          }
        }
      } catch (err) {
        console.warn('Error polling task status:', err);
      }
    };

    fetchStatus();
    const interval = setInterval(() => {
      if (task?.status === 'RUNNING' || task?.status === 'PENDING' || !task) {
        fetchStatus();
      }
    }, 2000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [isOpen, activeTaskId, task?.status]);

  // Load recent tasks
  useEffect(() => {
    if (!isOpen) return;
    const loadRecents = async () => {
      setIsLoading(true);
      try {
        const res = await listAcquisitionTasks(10);
        setRecentTasks(res.tasks || []);
      } catch (err) {
        console.warn('Failed to load recent tasks:', err);
      } finally {
        setIsLoading(false);
      }
    };
    loadRecents();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCancel = async () => {
    if (!activeTaskId) return;
    try {
      await cancelAcquisitionTask(activeTaskId);
      setActionMessage('已发送任务终止请求');
      const updated = await fetchAcquisitionTask(activeTaskId);
      setTask(updated);
    } catch (err: any) {
      setActionMessage(`终止失败: ${err.message}`);
    }
  };

  const handleResume = async () => {
    if (!activeTaskId) return;
    try {
      await resumeAcquisitionTask(activeTaskId);
      setActionMessage('已从断点恢复执行');
      const updated = await fetchAcquisitionTask(activeTaskId);
      setTask(updated);
    } catch (err: any) {
      setActionMessage(`恢复失败: ${err.message}`);
    }
  };

  const handleCleanupZombies = async () => {
    try {
      const res = await cleanupZombieTasks();
      setActionMessage(`清理完成: 共清理 ${res.cleaned_zombie_tasks_count} 个僵尸任务`);
      const updatedList = await listAcquisitionTasks(10);
      setRecentTasks(updatedList.tasks || []);
      if (activeTaskId) {
        const updated = await fetchAcquisitionTask(activeTaskId);
        setTask(updated);
      }
    } catch (err: any) {
      setActionMessage(`清理失败: ${err.message}`);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'SUCCESS':
        return (
          <span className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            SUCCESS
          </span>
        );
      case 'RUNNING':
        return (
          <span className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 animate-pulse">
            <RefreshCw className="w-3 h-3 animate-spin text-blue-600" />
            RUNNING
          </span>
        );
      case 'PARTIAL_SUCCESS':
        return (
          <span className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-300">
            <AlertTriangle className="w-3 h-3 text-amber-600" />
            PARTIAL
          </span>
        );
      case 'FAILED':
      case 'INTERRUPTED':
        return (
          <span className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-red-50 text-red-700 border border-red-200">
            <XCircle className="w-3 h-3 text-red-600" />
            {status}
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-warm-100 text-warm-600 border border-warm-200">
            <Square className="w-3 h-3 text-warm-500" />
            CANCELLED
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-warm-100 text-warm-600 border border-warm-200">
            <Clock className="w-3 h-3 text-warm-500" />
            {status}
          </span>
        );
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-xl bg-white shadow-2xl border-l border-warm-200 flex flex-col animate-in slide-in-from-right duration-200 select-none">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-warm-200 bg-warm-50/70 shrink-0">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-warm-700" />
          <h3 className="font-semibold text-warm-900 text-sm">行情采集与更新任务监视器</h3>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCleanupZombies}
            className="px-2 py-1 text-[11px] font-medium text-warm-600 hover:text-warm-900 hover:bg-warm-200/60 rounded border border-warm-200 flex items-center gap-1 transition-colors"
            title="清理失联超过120秒的僵尸任务"
          >
            <Trash2 className="w-3 h-3" />
            <span>巡检僵尸</span>
          </button>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-warm-400 hover:text-warm-700 hover:bg-warm-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {actionMessage && (
        <div className="px-5 py-2 bg-blue-50 text-blue-800 text-xs border-b border-blue-200 flex items-center justify-between">
          <span>{actionMessage}</span>
          <button onClick={() => setActionMessage(null)} className="text-blue-500 hover:text-blue-800">
            ×
          </button>
        </div>
      )}

      {/* Main Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Active Task Card */}
        {task ? (
          <div className="bg-white rounded-xl border border-warm-200 shadow-xs overflow-hidden">
            <div className="p-4 bg-warm-50/40 border-b border-warm-100 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-warm-800">{task.task_id}</span>
                  {getStatusBadge(task.status)}
                </div>
                <div className="text-[11px] text-warm-500 mt-0.5">
                  创建: {new Date(task.created_at).toLocaleTimeString()} | 周期: {task.timeframe} | 跨度: {task.start_date} ~ {task.end_date}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-1.5">
                {task.status === 'RUNNING' && (
                  <button
                    onClick={handleCancel}
                    className="px-2.5 py-1 text-xs font-medium bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 rounded-md transition-colors flex items-center gap-1"
                  >
                    <Square className="w-3 h-3" />
                    <span>终止</span>
                  </button>
                )}
                {(task.status === 'INTERRUPTED' || task.status === 'PARTIAL_SUCCESS' || task.status === 'FAILED') && (
                  <button
                    onClick={handleResume}
                    className="px-2.5 py-1 text-xs font-medium bg-warm-800 hover:bg-warm-900 text-white rounded-md transition-colors flex items-center gap-1 shadow-xs"
                  >
                    <Play className="w-3 h-3" />
                    <span>断点续传</span>
                  </button>
                )}
              </div>
            </div>

            {/* Progress Section */}
            <div className="p-4 space-y-3">
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-warm-600 font-medium">执行进度</span>
                  <span className="font-mono font-semibold text-warm-900">
                    {task.completed_symbols} / {task.total_symbols} 标的 ({task.progress_percent?.toFixed(1)}%)
                  </span>
                </div>
                <div className="w-full bg-warm-100 rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-full transition-all duration-300 ${
                      task.status === 'FAILED'
                        ? 'bg-red-500'
                        : task.status === 'SUCCESS'
                        ? 'bg-emerald-500'
                        : 'bg-warm-800'
                    }`}
                    style={{ width: `${task.progress_percent || 0}%` }}
                  />
                </div>
              </div>

              {/* Heartbeat Status */}
              <div className="flex items-center justify-between text-[11px] font-mono text-warm-500 pt-1 border-t border-warm-100">
                <span className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${task.status === 'RUNNING' ? 'bg-emerald-500 animate-ping' : 'bg-warm-300'}`} />
                  <span>最后心跳: {task.last_heartbeat_at ? new Date(task.last_heartbeat_at).toLocaleTimeString() : '--'}</span>
                </span>
                <span>失败项: {task.failed_symbols}</span>
              </div>
            </div>

            {/* Item Breakdown List */}
            {task.items && task.items.length > 0 && (
              <div className="border-t border-warm-100">
                <div className="px-4 py-2 bg-warm-50/50 text-xs font-medium text-warm-700">
                  标的执行明细 ({task.items.length})
                </div>
                <div className="divide-y divide-warm-100 max-h-56 overflow-y-auto">
                  {task.items.map((it) => (
                    <div key={it.item_id} className="px-4 py-2 text-xs flex items-center justify-between hover:bg-warm-50/50">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-warm-900">{it.symbol}</span>
                        <span className="text-[10px] text-warm-400 font-mono">
                          {it.row_count > 0 ? `${it.row_count} 行` : ''}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {it.execution_latency_ms && (
                          <span className="text-[10px] text-warm-400 font-mono">
                            {it.execution_latency_ms.toFixed(0)}ms
                          </span>
                        )}
                        {getStatusBadge(it.status)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="p-8 text-center bg-warm-50 rounded-xl border border-warm-200 border-dashed text-warm-400 text-xs">
            暂无选中的活动采集任务
          </div>
        )}

        {/* Recent Tasks List */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-warm-800">历史与近期任务</h4>
            {isLoading && <RefreshCw className="w-3 h-3 text-warm-400 animate-spin" />}
          </div>
          <div className="divide-y divide-warm-100 border border-warm-200 rounded-xl overflow-hidden bg-white shadow-xs">
            {recentTasks.length === 0 ? (
              <div className="p-4 text-center text-xs text-warm-400">暂无任务记录</div>
            ) : (
              recentTasks.map((t) => (
                <div
                  key={t.task_id}
                  onClick={() => onSelectTaskId(t.task_id)}
                  className={`p-3 text-xs flex items-center justify-between cursor-pointer hover:bg-warm-50 transition-colors ${
                    activeTaskId === t.task_id ? 'bg-warm-50/80 font-medium' : ''
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-warm-900 font-semibold">{t.task_id}</span>
                      {getStatusBadge(t.status)}
                    </div>
                    <div className="text-[11px] text-warm-400 mt-0.5">
                      {t.symbols.slice(0, 3).join(', ')} {t.symbols.length > 3 ? `等 ${t.symbols.length} 标的` : ''}
                    </div>
                  </div>
                  <div className="text-right font-mono text-[11px] text-warm-500">
                    <div>{t.completed_symbols}/{t.total_symbols}</div>
                    <div className="text-[10px] text-warm-400">{new Date(t.created_at).toLocaleTimeString()}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
