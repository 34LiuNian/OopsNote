"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Box,
  Heading,
  Text,
  Spinner,
} from "@primer/react";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { TaskActions } from "./task/TaskActions";
import { TaskProblemList } from "./task/TaskProblemList";
import { deleteTask } from "../features/tasks";
import { useTagDimensions } from "../features/tags";
import { useTaskStream } from "../hooks/useTaskStream";
import { useTaskProgress } from "../hooks/useTaskProgress";
import { TaskProgressBar } from "./task/TaskProgressBar";
import { ErrorBanner } from "./ErrorBanner";
import { TaskLiveStream } from "./task/TaskLiveStream";
import { TaskMathRenderer } from "./task/TaskMathRenderer";
import { TaskStatusToaster } from "./task/TaskStatusToaster";

// Format duration between two dates
function formatDuration(start: string, end: string): string {
  const startDate = new Date(start).getTime();
  const endDate = new Date(end).getTime();

  // Return "未知" for invalid dates
  if (Number.isNaN(startDate) || Number.isNaN(endDate)) return "未知";

  const diffMs = endDate - startDate;

  if (diffMs < 0) return "未知";

  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours > 0) {
    return `${hours}小时${remainingMinutes}分${remainingSeconds}秒`;
  } else if (minutes > 0) {
    return `${minutes}分${remainingSeconds}秒`;
  } else {
    return `${remainingSeconds}秒`;
  }
}

export function TaskLiveView({ taskId }: { taskId: string }) {
  const [data, setData] = useState<TaskResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const { effectiveDimensions: tagStyles } = useTagDimensions();
  const [editingKey, setEditingKey] = useState<string>("");

  const loadOnce = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const latest = await fetchJson<TaskResponse>(`/tasks/${taskId}`);
      setData(latest);
      const msg = latest.task.stage_message || latest.task.stage || latest.task.status;
      setStatusMessage(msg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务失败");
    } finally {
      setIsLoading(false);
    }
  }, [taskId]);

  const { progressLines: streamProgress, latestTask, resetStream } = useTaskStream({
    taskId,
    status: data?.task?.status,
    onStatusMessage: setStatusMessage,
    onDone: loadOnce,
  });

  // Update data with latest task from polling
  useEffect(() => {
    if (!latestTask) return;
    setData((prev) => {
      if (!prev) return { task: latestTask };
      // Only update if something changed
      if (prev.task.status === latestTask.status &&
          prev.task.stage === latestTask.stage &&
          prev.task.stage_message === latestTask.stage_message) {
        return prev;
      }
      return { task: latestTask };
    });
  }, [latestTask]);

  const cancelTask = useCallback(async () => {
    if (!data) return;
    const status = data.task.status;
    if (status !== "pending" && status !== "processing") return;

    setIsCancelling(true);
    setError("");
    try {
      await fetchJson<TaskResponse>(`/tasks/${taskId}/cancel`, { method: "POST" });
      await loadOnce();
    } catch (err) {
      setError(err instanceof Error ? err.message : "作废任务失败");
    } finally {
      setIsCancelling(false);
    }
  }, [data, loadOnce, taskId]);

  const retryTask = useCallback(async () => {
    if (!data) return;
    const status = data.task.status;
    if (status !== "failed" && status !== "completed" && status !== "cancelled") return;

    setIsRetrying(true);
    setError("");
    setStatusMessage("准备重试...");
    resetStream();

    try {
      await fetchJson<TaskResponse>(
        `/tasks/${taskId}/retry?background=true`,
        { method: "POST" }
      );
      await loadOnce();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重试失败");
    } finally {
      setIsRetrying(false);
    }
  }, [data, loadOnce, taskId]);


  const removeTask = useCallback(async () => {
    if (!window.confirm("确认删除这个任务（将删除其所有题目）？")) return;
    try {
      await deleteTask(taskId);
      window.location.href = "/library";
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除任务失败");
    }
  }, [taskId]);

  useEffect(() => {
    resetStream();
    void loadOnce();
  }, [loadOnce, resetStream]);

  const progressState = useTaskProgress({
    status: data?.task?.status,
    stage: data?.task?.stage,
    stageMessage: data?.task?.stage_message,
    statusMessage,
    streamProgress,
  });

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {/* Math renderer */}
      <TaskMathRenderer data={data} />

      {/* Status toaster */}
      <TaskStatusToaster statusMessage={statusMessage} status={data?.task?.status} />

      {/* Task header card */}
      <Box
        className="oops-card"
        sx={{ p: 4, position: "relative", overflow: "hidden" }}
      >
        {/* Subtle gradient accent bar at top */}
        <Box
          sx={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            background: data?.task?.status === "completed"
              ? "linear-gradient(90deg, var(--fgColor-success, #2da44e), var(--fgColor-done, #8250df))"
              : data?.task?.status === "failed"
                ? "linear-gradient(90deg, var(--fgColor-danger, #cf222e), var(--fgColor-attention, #bf8700))"
                : "linear-gradient(90deg, var(--fgColor-accent, #0969da), var(--fgColor-done, #8250df))",
            borderRadius: "var(--oops-radius-md) var(--oops-radius-md) 0 0",
          }}
        />

        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 3, flexWrap: "wrap" }}>
          <Box sx={{ flex: 1, minWidth: 200 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 1 }}>
              <Heading as="h2" sx={{ fontSize: 3, m: 0 }}>任务详情</Heading>
              <Box
                className={`oops-badge ${
                  data?.task?.status === "completed" ? "oops-badge-success"
                    : data?.task?.status === "failed" ? "oops-badge-danger"
                      : data?.task?.status === "processing" || data?.task?.status === "pending" ? "oops-badge-accent"
                        : "oops-badge-muted"
                }`}
              >
                {data?.task?.status === "completed" ? "已完成"
                  : data?.task?.status === "failed" ? "失败"
                    : data?.task?.status === "processing" ? "处理中"
                      : data?.task?.status === "pending" ? "排队中"
                        : data?.task?.status === "cancelled" ? "已取消"
                          : data?.task?.status ?? "加载中"}
              </Box>
            </Box>
            <Text sx={{ fontSize: 0, color: "fg.muted", fontFamily: "mono" }}>{taskId}</Text>
            {data?.task?.created_at && (
              <Box sx={{ mt: 2, display: "flex", gap: 3, flexWrap: "wrap" }}>
                <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                  创建：{new Date(data.task.created_at).toLocaleString("zh-CN")}
                </Text>
                {(data.task.status === "completed" || data.task.status === "failed" || data.task.status === "cancelled") && data.task.updated_at && (
                  <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                    用时：{formatDuration(data.task.created_at, data.task.updated_at)}
                  </Text>
                )}
              </Box>
            )}
          </Box>
          <TaskActions
            status={data?.task?.status}
            isCancelling={isCancelling}
            isRetrying={isRetrying}
            isLoading={isLoading}
            onCancel={cancelTask}
            onRetry={retryTask}
            onRefresh={loadOnce}
            onDelete={removeTask}
          />
        </Box>
      </Box>

      {/* Progress bar */}
      <TaskProgressBar
        progressState={progressState}
        latestLine={progressState.latestLine}
        error={error}
        statusMessage={statusMessage}
      />

      <ErrorBanner message={error} />

      {(data?.task?.status === "pending" || data?.task?.status === "processing") && (
        <TaskLiveStream streamProgress={streamProgress} />
      )}

      {!error && !data && (
        <Box className="oops-empty-state" sx={{ py: 6 }}>
          <Spinner size="medium" />
          <Text as="p" sx={{ color: "fg.muted" }}>正在加载任务数据...</Text>
        </Box>
      )}

      {data && (
        <TaskProblemList
          taskId={taskId}
          problems={data.task.problems}
          solutions={data.task.solutions}
          tags={data.task.tags}
          editingKey={editingKey}
          onEdit={setEditingKey}
          onCloseEdit={() => setEditingKey("")}
          onSaved={loadOnce}
          tagStyles={tagStyles}
          onStatusMessage={setStatusMessage}
          onError={setError}
        />
      )}

      {/* Bottom navigation */}
      <Box sx={{ display: "flex", gap: 3, pt: 2, borderTop: "1px solid", borderColor: "border.muted", fontSize: 1 }}>
        <Link href="/" style={{ textDecoration: "none" }}>
          <Text as="span" sx={{ color: "accent.fg", fontWeight: 500, "&:hover": { textDecoration: "underline" } }}>← 采集面板</Text>
        </Link>
        <Link href="/library" style={{ textDecoration: "none" }}>
          <Text as="span" sx={{ color: "accent.fg", fontWeight: 500, "&:hover": { textDecoration: "underline" } }}>题库总览</Text>
        </Link>
      </Box>
    </Box>
  );
}
