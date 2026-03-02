"use client";

import { useCallback, useState } from "react";
import { formatApiError } from "./errors";
import { getDebugSettings, updateDebugSettings } from "./api";
import type { DebugSettingsResponse } from "../../types/api";

type UseDebugSettingsState = {
  settings: DebugSettingsResponse | null;
  isLoading: boolean;
  isSaving: boolean;
  statusMessage: string;
  errorMessage: string;
  refresh: () => Promise<void>;
  toggle: (field: "debug_llm_payload" | "persist_tasks", value: boolean) => Promise<void>;
};

export function useDebugSettings(): UseDebugSettingsState {
  const [settings, setSettings] = useState<DebugSettingsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getDebugSettings();
      setSettings(data);
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载调试设置失败"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const toggle = useCallback(
    async (field: "debug_llm_payload" | "persist_tasks", value: boolean) => {
      setIsSaving(true);
      setErrorMessage("");
      setStatusMessage("");
      try {
        const data = await updateDebugSettings({ [field]: value });
        setSettings(data);
        setStatusMessage("调试设置已更新。");
      } catch (err) {
        setErrorMessage(formatApiError(err, "更新调试设置失败"));
      } finally {
        setIsSaving(false);
      }
    },
    []
  );

  return {
    settings,
    isLoading,
    isSaving,
    statusMessage,
    errorMessage,
    refresh,
    toggle,
  };
}
