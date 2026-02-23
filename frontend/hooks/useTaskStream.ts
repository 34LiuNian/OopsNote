"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";

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
  resetStream: () => void;
};

export function useTaskStream({ taskId, status, onStatusMessage, onDone }: UseTaskStreamParams): UseTaskStreamState {
  const [progressLines, setProgressLines] = useState<string[]>([]);
  const pollingIntervalRef = useRef<number | null>(null);
  const lastStatusRef = useRef<string | null>(null);
  const hasCalledOnDoneRef = useRef<boolean>(false);

  const resetStream = useCallback(() => {
    setProgressLines([]);
    lastStatusRef.current = null;
    hasCalledOnDoneRef.current = false;
  }, []);

  useEffect(() => {
    if (!taskId) return;

    // Only poll if task is actively processing
    const isActive = status === "pending" || status === "processing";
    if (!isActive) {
      // Clear polling if not active
      if (pollingIntervalRef.current) {
        window.clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
      return;
    }

    // Clear any existing polling
    if (pollingIntervalRef.current) {
      window.clearInterval(pollingIntervalRef.current);
    }

    // Start polling
    const startPolling = () => {
      if (DEBUG) console.log('[useTaskStream] starting polling for task:', taskId, 'status:', status);

      const poll = async () => {
        try {
          const payload = await fetchJson<TaskResponse>(`/tasks/${taskId}`);
          const task = payload.task;
          const currentStatus = task.status;

          if (DEBUG) console.log('[useTaskStream] polled task status:', currentStatus, 'last status:', lastStatusRef.current);

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
              if (pollingIntervalRef.current) {
                window.clearInterval(pollingIntervalRef.current);
                pollingIntervalRef.current = null;
              }
            }
          }
        } catch (error) {
          if (DEBUG) console.error('[useTaskStream] polling error:', error);
          onStatusMessage?.("轮询失败：" + (error instanceof Error ? error.message : "未知错误"));
        }
      };

      // Poll immediately
      poll();

      // Then poll at regular intervals
      pollingIntervalRef.current = window.setInterval(poll, POLLING_INTERVAL);
    };

    startPolling();

    // Cleanup
    return () => {
      if (pollingIntervalRef.current) {
        window.clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [taskId, status, onStatusMessage, onDone]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        window.clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, []);

  return {
    progressLines,
    resetStream,
  };
}
