"use client";

import Link from "next/link";
import { AlertTriangle, ListChecks, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { SUBJECT_OPTIONS } from "@/config/subjects";
import { deleteTask, retryTask } from "@/features/tasks";
import { API_BASE } from "@/lib/api";
import { formatApiError } from "@/lib/errorFormatter";
import { notify } from "@/lib/notify";
import type { TaskStage, TaskSummary } from "@/types/api";
import { Box, Button, Spinner, Text } from "@/components/ui/primitives";

const STAGE_LABELS: Partial<Record<TaskStage, string>> = {
  queued: "等待处理",
  starting: "启动任务",
  ocr: "识别题目",
  solving: "生成解答",
  verifying: "校验内容",
  tagging: "整理标签",
  finalizing: "保存结果",
  syncing: "同步数据",
};

const SUBJECT_LABELS = Object.fromEntries(
  SUBJECT_OPTIONS.map((subject) => [subject.value, subject.label]),
);

function formatFailureTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function failureReason(task: TaskSummary) {
  const message = task.stage_message?.trim();
  return message || "处理过程中发生异常。打开详情可查看完整运行记录。";
}

function cardLayoutClass(ratio?: number) {
  if (!ratio) return "is-layout-pending";
  if (ratio >= 3.6) return "is-panorama";
  if (ratio >= 2) return "is-wide";
  if (ratio < 0.9) return "is-tall";
  return "is-regular";
}

export function FailedTaskPanel({
  tasks,
  isLoading,
  refreshFailedTasks,
  refreshActiveTasks,
}: {
  tasks: TaskSummary[];
  isLoading: boolean;
  refreshFailedTasks: () => Promise<void>;
  refreshActiveTasks: () => Promise<void>;
}) {
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [retryingIds, setRetryingIds] = useState<Record<string, boolean>>({});
  const [deletingIds, setDeletingIds] = useState<Record<string, boolean>>({});
  const [isBatchRetrying, setIsBatchRetrying] = useState(false);
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);
  const [imageRatios, setImageRatios] = useState<Record<string, number>>({});

  const selectedCount = tasks.filter((task) => selectedIds[task.id]).length;
  const isBatchBusy = isBatchRetrying || isBatchDeleting;

  useEffect(() => {
    const taskIds = new Set(tasks.map((task) => task.id));
    setSelectedIds((current) => Object.fromEntries(
      Object.entries(current).filter(([taskId, selected]) => selected && taskIds.has(taskId)),
    ));
  }, [tasks]);

  const leaveSelectionMode = useCallback(() => {
    setSelectionMode(false);
    setSelectedIds({});
  }, []);

  const retryOne = useCallback(async (taskId: string) => {
    if (retryingIds[taskId]) return;
    setRetryingIds((current) => ({ ...current, [taskId]: true }));
    try {
      await retryTask(taskId, true);
      notify.success({ title: "已重新提交，可在进行中查看" });
      await Promise.all([refreshFailedTasks(), refreshActiveTasks()]);
    } catch (error) {
      notify.error({ title: formatApiError(error, "重新处理失败，请稍后再试") });
    } finally {
      setRetryingIds((current) => ({ ...current, [taskId]: false }));
    }
  }, [refreshActiveTasks, refreshFailedTasks, retryingIds]);

  const retrySelected = useCallback(async () => {
    const taskIds = tasks.filter((task) => selectedIds[task.id]).map((task) => task.id);
    if (taskIds.length === 0 || isBatchRetrying) return;

    setIsBatchRetrying(true);
    try {
      const results = await Promise.allSettled(taskIds.map((taskId) => retryTask(taskId, true)));
      const successCount = results.filter((result) => result.status === "fulfilled").length;
      const failedCount = results.length - successCount;
      if (successCount > 0) notify.success({ title: `已重新提交 ${successCount} 个任务` });
      if (failedCount > 0) notify.error({ title: `${failedCount} 个任务未能重新提交` });
      leaveSelectionMode();
      await Promise.all([refreshFailedTasks(), refreshActiveTasks()]);
    } catch (error) {
      notify.error({ title: formatApiError(error, "批量重新处理失败，请稍后再试") });
    } finally {
      setIsBatchRetrying(false);
    }
  }, [isBatchRetrying, leaveSelectionMode, refreshActiveTasks, refreshFailedTasks, selectedIds, tasks]);

  const deleteOne = useCallback(async (taskId: string) => {
    if (deletingIds[taskId]) return;
    if (!window.confirm("删除这个失败任务？任务记录将从列表移除，且无法撤销。")) return;

    setDeletingIds((current) => ({ ...current, [taskId]: true }));
    try {
      await deleteTask(taskId);
      notify.success({ title: "失败任务已删除" });
      await refreshFailedTasks();
    } catch (error) {
      notify.error({ title: formatApiError(error, "删除任务失败，请稍后再试") });
    } finally {
      setDeletingIds((current) => ({ ...current, [taskId]: false }));
    }
  }, [deletingIds, refreshFailedTasks]);

  const deleteSelected = useCallback(async () => {
    const taskIds = tasks.filter((task) => selectedIds[task.id]).map((task) => task.id);
    if (taskIds.length === 0 || isBatchBusy) return;
    if (!window.confirm(`删除选中的 ${taskIds.length} 个失败任务？任务记录将从列表移除，且无法撤销。`)) return;

    setIsBatchDeleting(true);
    try {
      const results = await Promise.allSettled(taskIds.map((taskId) => deleteTask(taskId)));
      const successCount = results.filter((result) => result.status === "fulfilled").length;
      const failedCount = results.length - successCount;
      if (successCount > 0) notify.success({ title: `已删除 ${successCount} 个失败任务` });
      if (failedCount > 0) notify.error({ title: `${failedCount} 个任务未能删除` });
      leaveSelectionMode();
      await refreshFailedTasks();
    } catch (error) {
      notify.error({ title: formatApiError(error, "批量删除失败，请稍后再试") });
    } finally {
      setIsBatchDeleting(false);
    }
  }, [isBatchBusy, leaveSelectionMode, refreshFailedTasks, selectedIds, tasks]);

  if (isLoading && tasks.length === 0) {
    return <Box className="failed-task-panel__loading"><Spinner size="small" /></Box>;
  }

  if (tasks.length === 0) {
    return (
      <Box className="failed-task-panel__empty">
        <Text sx={{ fontWeight: 600 }}>没有待处理的失败任务</Text>
        <Text sx={{ color: "fg.muted", fontSize: 1 }}>重新提交的任务会出现在“进行中”。</Text>
      </Box>
    );
  }

  return (
    <Box className="failed-task-panel">
      <Box className="failed-task-panel__summary">
        <Box className="failed-task-panel__summary-icon" aria-hidden="true">
          <AlertTriangle size={18} />
        </Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Text sx={{ fontWeight: 650 }}>{tasks.length} 个任务需要处理</Text>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>
            先确认失败原因，再重新处理；每次重试都会创建一次新的运行记录。
          </Text>
        </Box>
        {!selectionMode && (
          <Button size="small" variant="secondary" leadingVisual={ListChecks} onClick={() => setSelectionMode(true)}>
            批量处理
          </Button>
        )}
      </Box>

      {selectionMode && (
        <Box className="failed-task-panel__batch" role="toolbar" aria-label="批量处理失败任务">
          <Text sx={{ fontWeight: 600, fontSize: 1 }} aria-live="polite">
            已选 {selectedCount} 项
          </Text>
          <Button
            size="small"
            variant="invisible"
            onClick={() => setSelectedIds(Object.fromEntries(tasks.map((task) => [task.id, true])))}
          >
            全选
          </Button>
          <Button size="small" variant="invisible" onClick={() => setSelectedIds({})} disabled={selectedCount === 0}>
            清空
          </Button>
          <Box sx={{ flex: 1 }} />
          <Button
            size="small"
            variant="danger"
            leadingVisual={Trash2}
            disabled={selectedCount === 0 || isBatchBusy}
            onClick={() => void deleteSelected()}
          >
            {isBatchDeleting ? "正在删除…" : `删除 (${selectedCount})`}
          </Button>
          <Button size="small" variant="invisible" onClick={leaveSelectionMode} disabled={isBatchBusy}>
            取消
          </Button>
          <Button
            size="small"
            variant="primary"
            leadingVisual={RefreshCw}
            disabled={selectedCount === 0 || isBatchBusy}
            onClick={() => void retrySelected()}
          >
            {isBatchRetrying ? "正在提交…" : `重新处理 (${selectedCount})`}
          </Button>
        </Box>
      )}

      <Box className="failed-task-panel__grid">
        {tasks.map((task) => {
          const isSelected = !!selectedIds[task.id];
          const isRetrying = !!retryingIds[task.id];
          const isDeleting = !!deletingIds[task.id];
          const layoutClass = cardLayoutClass(imageRatios[task.id]);
          const toggleSelected = () => setSelectedIds((current) => ({
            ...current,
            [task.id]: !current[task.id],
          }));
          return (
            <Box
              key={task.id}
              as="article"
              className={`failed-task-card ${layoutClass}${selectionMode ? " is-selectable" : ""}${isSelected ? " is-selected" : ""}`}
              role={selectionMode ? "button" : undefined}
              tabIndex={selectionMode ? 0 : undefined}
              aria-pressed={selectionMode ? isSelected : undefined}
              onClick={selectionMode ? toggleSelected : undefined}
              onKeyDown={selectionMode ? (event) => {
                if (event.key !== "Enter" && event.key !== " ") return;
                event.preventDefault();
                toggleSelected();
              } : undefined}
            >
              <Box
                className="failed-task-card__image"
                aria-hidden="true"
              >
                {task.asset?.path ? (
                  <img
                    src={`${API_BASE}${task.asset.path}`}
                    alt=""
                    onLoad={(event) => {
                      const image = event.currentTarget;
                      if (!image.naturalWidth || !image.naturalHeight) return;
                      setImageRatios((current) => ({
                        ...current,
                        [task.id]: image.naturalWidth / image.naturalHeight,
                      }));
                    }}
                  />
                ) : (
                  <span>暂无题图</span>
                )}
              </Box>
              <Box className="failed-task-card__scrim" aria-hidden="true" />
              <Box className="failed-task-card__content">
                <Box className="failed-task-card__meta">
                  <span className="oops-badge oops-badge-danger">
                    {task.stage ? STAGE_LABELS[task.stage] || "处理失败" : "处理失败"}
                  </span>
                  <Text as="span" sx={{ color: "fg.muted", fontSize: 0 }}>
                    {SUBJECT_LABELS[task.subject] || task.subject || "未分类"}
                    {task.question_no ? ` · 第 ${task.question_no} 题` : ""}
                    {` · ${formatFailureTime(task.updated_at)}`}
                  </Text>
                </Box>
                <Text className="failed-task-card__reason" title={failureReason(task)}>
                  {failureReason(task)}
                </Text>
              </Box>
              {!selectionMode && (
                <Box className="failed-task-card__actions">
                  <Button
                    size="small"
                    variant="primary"
                    disabled={isRetrying || isDeleting}
                    onClick={() => void retryOne(task.id)}
                  >
                    {isRetrying ? "正在提交…" : "重新处理"}
                  </Button>
                  <Link className="failed-task-card__detail" href={`/tasks/${task.id}`}>
                    查看详情
                  </Link>
                  <Button
                    size="small"
                    variant="danger"
                    disabled={isRetrying || isDeleting}
                    onClick={() => void deleteOne(task.id)}
                  >
                    {isDeleting ? "正在删除…" : "删除"}
                  </Button>
                </Box>
              )}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
