"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ProblemSummary } from "../../types/api";
import { listProblems, type ListProblemsParams } from "./api";

type UseProblemListState = {
  items: ProblemSummary[];
  isLoading: boolean;
  error: string;
  refresh: () => Promise<void>;
};

export function useProblemList(params?: ListProblemsParams): UseProblemListState {
  const [items, setItems] = useState<ProblemSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const paramsKey = JSON.stringify(params ?? {});
  const stableParams = useMemo(() => params ?? {}, [paramsKey]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const data = await listProblems(stableParams);
      setItems(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载题库失败");
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
