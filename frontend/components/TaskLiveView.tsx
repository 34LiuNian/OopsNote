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
    <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
      {/* Math renderer */}
      <TaskMathRenderer data={data} />

      {/* Status toaster */}
      <TaskStatusToaster statusMessage={statusMessage} status={data?.task?.status} />
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Task</Text>
          <Heading as="h2" sx={{ fontSize: 3 }}>任务 {taskId}</Heading>
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
        <Box sx={{ textAlign: 'center', p: 4, color: 'fg.muted' }}>
          <Spinner size="medium" sx={{ mb: 2 }} />
          <Text as="p">正在加载任务数据...</Text>
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

      <Box sx={{ mt: 4, pt: 3, borderTop: '1px solid', borderColor: 'border.muted', fontSize: 1 }}>
        <Link href="/">
          <Text as="span" sx={{ color: 'accent.fg', textDecoration: 'none', mr: 2, cursor: 'pointer' }}>返回采集面板</Text>
        </Link>
        <Text sx={{ color: 'fg.muted' }}>·</Text>
        <Link href="/library">
          <Text as="span" sx={{ color: 'accent.fg', textDecoration: 'none', ml: 2, cursor: 'pointer' }}>返回题库总览</Text>
        </Link>
      </Box>
    </Box>
  );
}
