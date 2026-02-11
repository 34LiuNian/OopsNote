"use client";

import { useCallback, useState } from "react";
import type { ModelsResponse } from "../../types/api";
import { formatApiError } from "./errors";
import { listModels } from "./api";

type UseModelListState = {
  items: ModelsResponse["items"];
  isLoading: boolean;
  errorMessage: string;
  refresh: (refreshFromServer: boolean) => Promise<void>;
};

export function useModelList(): UseModelListState {
  const [items, setItems] = useState<ModelsResponse["items"]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const refresh = useCallback(async (refreshFromServer: boolean) => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await listModels(refreshFromServer);
      setItems(data.items ?? []);
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载模型列表失败"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    items,
    isLoading,
    errorMessage,
    refresh,
  };
}
