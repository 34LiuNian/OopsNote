"use client";

import { useCallback, useState } from "react";
import { formatApiError } from "./errors";
import { getDebugSettings, updateDebugSettings } from "./api";
import type { DebugSettingsResponse } from "../../types/api";

type UseDebugSettingsState = {
  settings: DebugSettingsResponse | null;
  draft: DebugSettingsResponse | null;
  isLoading: boolean;
  isSaving: boolean;
  isDirty: boolean;
  statusMessage: string;
  errorMessage: string;
  refresh: () => Promise<void>;
  setDraftValue: (field: "debug_llm_payload" | "persist_tasks", value: boolean) => void;
  reset: () => void;
  save: () => Promise<void>;
};

export function useDebugSettings(): UseDebugSettingsState {
  const [settings, setSettings] = useState<DebugSettingsResponse | null>(null);
  const [draft, setDraft] = useState<DebugSettingsResponse | null>(null);
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
      setDraft(data);
    } catch (err) {
      setErrorMessage(formatApiError(err, "Failed to load debug settings"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setDraftValue = useCallback((field: "debug_llm_payload" | "persist_tasks", value: boolean) => {
    setDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
  }, []);

  const reset = useCallback(() => {
    setDraft(settings);
    setStatusMessage("");
    setErrorMessage("");
  }, [settings]);

  const isDirty =
    settings != null &&
    draft != null &&
    (settings.debug_llm_payload !== draft.debug_llm_payload ||
      settings.persist_tasks !== draft.persist_tasks);

  const save = useCallback(async () => {
    if (!draft) return;
    setIsSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const data = await updateDebugSettings(draft);
      setSettings(data);
      setDraft(data);
      setStatusMessage("Debug settings saved");
    } catch (err) {
      setErrorMessage(formatApiError(err, "Failed to save debug settings"));
    } finally {
      setIsSaving(false);
    }
  }, [draft]);

  return {
    settings,
    draft,
    isLoading,
    isSaving,
    isDirty,
    statusMessage,
    errorMessage,
    refresh,
    setDraftValue,
    reset,
    save,
  };
}
