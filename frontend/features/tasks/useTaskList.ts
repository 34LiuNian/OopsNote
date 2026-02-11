"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { TaskSummary } from "../../types/api";
import { listTasks, type ListTasksParams } from "./api";

type UseTaskListState = {
  items: TaskSummary[];
  isLoading: boolean;
  error: string;
  refresh: () => Promise<void>;
};

function sameTasks(prev: TaskSummary[], next: TaskSummary[]): boolean {
  if (prev.length !== next.length) return false;
  for (let i = 0; i < prev.length; i += 1) {
    const a = prev[i];
    const b = next[i];
    if (a.id !== b.id) return false;
    if (a.status !== b.status) return false;
    if ((a.stage_message || a.stage || "") !== (b.stage_message || b.stage || "")) return false;
  }
  return true;
}

export function useTaskList(params?: ListTasksParams): UseTaskListState {
  const [items, setItems] = useState<TaskSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const paramsKey = JSON.stringify(params ?? {});
  const stableParams = useMemo(() => params ?? {}, [paramsKey]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const data = await listTasks(stableParams);
      setItems((prev) => (sameTasks(prev, data.items) ? prev : data.items));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务失败");
    } finally {
      setIsLoading(false);
    }
  }, [stableParams]);

  useEffect(() => {
    void refresh();
  }, [refresh, paramsKey]);

  return {
    items,
    isLoading,
    error,
    refresh,
  };
}
