"use client";

import { useEffect, useMemo } from "react";
import type { TaskSummary } from "../../types/api";
import { useTaskList } from "./useTaskList";
import type { ListTasksParams } from "./api";

type UseActiveTaskListState = {
  items: TaskSummary[];
  activeItems: TaskSummary[];
  isLoading: boolean;
  error: string;
  refresh: () => Promise<void>;
};

type UseActiveTaskListOptions = {
  pollIntervalMs?: number;
};

export function useActiveTaskList(
  params?: ListTasksParams,
  options: UseActiveTaskListOptions = {},
): UseActiveTaskListState {
  const { items, isLoading, error, refresh } = useTaskList(params);
  const activeItems = useMemo(
    () => items.filter((t) => t.status === "pending" || t.status === "processing"),
    [items],
  );
  const pollIntervalMs = options.pollIntervalMs ?? 1500;

  useEffect(() => {
    if (activeItems.length === 0) return;
    const timer = window.setInterval(async () => {
      try {
        await refresh();
      } catch {
        // ignore polling errors
      }
    }, pollIntervalMs);
    return () => {
      window.clearInterval(timer);
    };
  }, [activeItems.length, pollIntervalMs, refresh]);

  return {
    items,
    activeItems,
    isLoading,
    error,
    refresh,
  };
}
