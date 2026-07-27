"use client";

import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { TagDimensionStyle } from "../../types/api";
import { ensureTagDimensionStyles } from "./constants";
import { getTagDimensions, updateTagDimensions } from "./api";
import { queryKeys } from "../../lib/queryClient";

export function useTagDimensions() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.tags.dimensions(),
    queryFn: getTagDimensions,
  });
  const { data, isLoading, isFetching, error, refetch } = query;
  const dimensions = data?.dimensions ?? {};
  const effectiveDimensions = ensureTagDimensionStyles(dimensions);

  const save = useCallback(async () => {
    const saved = await updateTagDimensions({ dimensions: effectiveDimensions });
    queryClient.setQueryData(queryKeys.tags.dimensions(), saved);
    return saved;
  }, [effectiveDimensions, queryClient]);

  const setDimensions = useCallback((next: Record<string, TagDimensionStyle>) => {
    queryClient.setQueryData(queryKeys.tags.dimensions(), { dimensions: next });
  }, [queryClient]);

  const refresh = useCallback(async () => {
    await refetch();
  }, [refetch]);

  return {
    dimensions,
    setDimensions,
    effectiveDimensions,
    isLoading: isLoading || isFetching,
    error: error instanceof Error ? error.message : error ? "加载标签配置失败" : "",
    refresh,
    save,
  };
}
