"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { TaskSummary } from "../../types/api";
import { queryKeys } from "../../lib/queryClient";
import { listTasks, type ListTasksParams } from "./api";

type UseTaskListState = {
  items: TaskSummary[];
  isLoading: boolean;
  error: string;
  refresh: () => Promise<void>;
};

export function useTaskList(params?: ListTasksParams): UseTaskListState {
  const paramsKey = JSON.stringify(params ?? {});
  const stableParams = useMemo(() => params ?? {}, [paramsKey]);
  const query = useQuery({
    queryKey: [...queryKeys.tasks.lists(), stableParams],
    queryFn: () => listTasks(stableParams),
    staleTime: 15_000,
  });

  return {
    items: query.data?.items ?? [],
    isLoading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : "",
    refresh: async () => {
      await query.refetch();
    },
  };
}
