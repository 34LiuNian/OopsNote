"use client";

import { useCallback, useState } from "react";
import { formatApiError } from "./errors";
import { getSystemInfo } from "./api";
import type { SystemInfoResponse } from "../../types/api";

type UseSystemInfoState = {
  info: SystemInfoResponse | null;
  isLoading: boolean;
  errorMessage: string;
  refresh: () => Promise<void>;
};

export function useSystemInfo(): UseSystemInfoState {
  const [info, setInfo] = useState<SystemInfoResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getSystemInfo();
      setInfo(data);
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载系统信息失败"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    info,
    isLoading,
    errorMessage,
    refresh,
  };
}
