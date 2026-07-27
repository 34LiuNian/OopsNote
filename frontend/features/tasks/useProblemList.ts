"use client";

import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ProblemSummary } from "../../types/api";
import { listProblems, type ListProblemsParams } from "./api";
import { queryKeys } from "../../lib/queryClient";

type UseProblemListState = {
  items: ProblemSummary[];
  isLoading: boolean;
  error: string;
  refresh: () => Promise<void>;
};

export function useProblemList(params?: ListProblemsParams): UseProblemListState {
  const paramsKey = JSON.stringify(params ?? {});
  const query = useQuery({
    queryKey: queryKeys.problems.list(paramsKey),
    queryFn: () => listProblems(params),
  });
  const { data, isLoading, isFetching, error, refetch } = query;
  const refresh = useCallback(async () => {
    await refetch();
  }, [refetch]);

  return {
    items: data?.items ?? [],
    isLoading: isLoading || isFetching,
    error: error instanceof Error ? error.message : error ? "加载题库失败" : "",
    refresh,
  };
}
