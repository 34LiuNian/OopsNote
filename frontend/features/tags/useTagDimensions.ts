"use client";

import { useCallback, useEffect, useState } from "react";
import type { TagDimensionStyle } from "../../types/api";
import { ensureTagDimensionStyles } from "./constants";
import { getTagDimensions, updateTagDimensions } from "./api";

export function useTagDimensions() {
  const [dimensions, setDimensions] = useState<Record<string, TagDimensionStyle>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>("");

  const effectiveDimensions = ensureTagDimensionStyles(dimensions);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const data = await getTagDimensions();
      setDimensions(data.dimensions || {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载标签配置失败");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const save = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const saved = await updateTagDimensions({ dimensions: effectiveDimensions });
      setDimensions(saved.dimensions || {});
      return saved;
    } finally {
      setIsLoading(false);
    }
  }, [effectiveDimensions]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    dimensions,
    setDimensions,
    effectiveDimensions,
    isLoading,
    error,
    refresh,
    save,
  };
}
