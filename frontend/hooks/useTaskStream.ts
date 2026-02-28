"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { useInterval } from "./useInterval";

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
  const [latestTask, setLatestTask] = useState<TaskResponse["task"] | null>(null);
  const lastStatusRef = useRef<string | null>(null);
  const hasCalledOnDoneRef = useRef<boolean>(false);
  const { start: startPolling, stop: stopPolling } = useInterval();

  const resetStream = useCallback(() => {
    setProgressLines([]);
    setLatestTask(null);
    lastStatusRef.current = null;
    hasCalledOnDoneRef.current = false;
  }, []);

  const poll = useCallback(async () => {
    try {
      const payload = await fetchJson<TaskResponse>(`/tasks/${taskId}`);
      const task = payload.task;
      const currentStatus = task.status;

      if (DEBUG) console.log('[useTaskStream] polled task status:', currentStatus, 'last status:', lastStatusRef.current);

      // Always update latest task
      setLatestTask(task);

      // Check if status changed
      if (currentStatus !== lastStatusRef.current) {
        const message = task.stage_message || task.stage || currentStatus || "处理中";
        onStatusMessage?.(message);
        setProgressLines((prev) => {
          if (prev.length > 0 && prev[prev.length - 1] === message) return prev;
          return [...prev, message];
        });
        lastStatusRef.current = currentStatus;

        // Check if task is done
        if (currentStatus === "completed" || currentStatus === "failed" || currentStatus === "cancelled") {
          if (!hasCalledOnDoneRef.current) {
            hasCalledOnDoneRef.current = true;
            await onDone?.();
          }
          // Stop polling
          stopPolling();
        }
      }
    } catch (error) {
      if (DEBUG) console.error('[useTaskStream] polling error:', error);
      onStatusMessage?.("轮询失败：" + (error instanceof Error ? error.message : "未知错误"));
    }
  }, [taskId, onStatusMessage, onDone, stopPolling]);
  useEffect(() => {
    if (!taskId) return;

    // Only poll if task is actively processing
    const isActive = status === "pending" || status === "processing";
    if (!isActive) {
      stopPolling();
      return;
    }

    if (DEBUG) console.log('[useTaskStream] starting polling for task:', taskId, 'status:', status);

    // Start polling with immediate first call
    startPolling(poll, POLLING_INTERVAL);

    // Cleanup on unmount or taskId change
    return () => {
      stopPolling();
    };
  }, [taskId, status, poll, startPolling, stopPolling]);

  return {
    progressLines,
    latestTask,
    resetStream,
  };
}
