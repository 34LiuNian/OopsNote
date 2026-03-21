"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { queryKeys } from "../lib/queryClient";

// Debug flag - disabled in production
const DEBUG = typeof process !== 'undefined' && process.env?.NODE_ENV === 'development';

// Polling interval in milliseconds
const POLLING_INTERVAL = 1000; // 1 second

type UseTaskStreamParams = {
  taskId: string;
  status?: string | null;
  onStatusMessage?: (message: string) => void;
  onDone?: () => Promise<void> | void;
};

type UseTaskStreamState = {
  progressLines: string[];
  latestTask: TaskResponse["task"] | null;
  resetStream: () => void;
};

export function useTaskStream({ taskId, status, onStatusMessage, onDone }: UseTaskStreamParams): UseTaskStreamState {
  const [progressLines, setProgressLines] = useState<string[]>([]);
  const lastStatusRef = useRef<string | null>(null);
  const lastStageRef = useRef<string | null>(null);
  const lastStageMessageRef = useRef<string | null>(null);
  const hasCalledOnDoneRef = useRef<boolean>(false);
  const queryClient = useQueryClient();

  const resetStream = useCallback(() => {
    setProgressLines([]);
    lastStatusRef.current = null;
    lastStageRef.current = null;
    lastStageMessageRef.current = null;
    hasCalledOnDoneRef.current = false;
  }, []);

  // Use React Query with polling
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.tasks.detail(taskId),
    queryFn: () => fetchJson<TaskResponse>(`/tasks/${taskId}`),
    enabled: !!taskId,
    // 轮询配置
    refetchInterval: (status === "pending" || status === "processing") ? POLLING_INTERVAL : false,
    // 不缓存，总是获取最新
    staleTime: 0,
    // 网络错误时重试
    retry: 3,
    retryDelay: 1000,
  });

  // 处理任务状态变化
  useEffect(() => {
    if (!data?.task) return;

    const task = data.task;
    const currentStatus = task.status;

    if (DEBUG) console.log('[useTaskStream] task status:', currentStatus, 'last status:', lastStatusRef.current);

    const currentStage = task.stage || null;
    const currentStageMessage = task.stage_message || null;
    const statusChanged = currentStatus !== lastStatusRef.current;
    const stageChanged = currentStage !== lastStageRef.current;
    const stageMessageChanged = currentStageMessage !== lastStageMessageRef.current;

    // Append progress line when status/stage/stage_message changes
    if (statusChanged || stageChanged || stageMessageChanged) {
      const message = currentStageMessage || currentStage || currentStatus || "处理中";
      onStatusMessage?.(message);
      setProgressLines((prev) => {
        if (prev.length > 0 && prev[prev.length - 1] === message) return prev;
        return [...prev, message];
      });
    }

    if (statusChanged) {
      lastStatusRef.current = currentStatus;

      // Check if task is done
      if (currentStatus === "completed" || currentStatus === "failed" || currentStatus === "cancelled") {
        if (!hasCalledOnDoneRef.current) {
          hasCalledOnDoneRef.current = true;
          onDone?.();
        }
      }
    }

    if (stageChanged) {
      lastStageRef.current = currentStage;
    }

    if (stageMessageChanged) {
      lastStageMessageRef.current = currentStageMessage;
    }
  }, [data, onStatusMessage, onDone]);

  // 处理错误
  useEffect(() => {
    if (error) {
      if (DEBUG) console.error('[useTaskStream] query error:', error);
      onStatusMessage?.("轮询失败：" + (error instanceof Error ? error.message : "未知错误"));
    }
  }, [error, onStatusMessage]);

  return {
    progressLines,
    latestTask: data?.task || null,
    resetStream,
  };
}
