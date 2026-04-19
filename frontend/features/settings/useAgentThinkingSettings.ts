"use client";

import { useCallback, useState } from "react";
import { formatApiError } from "./errors";
import { getAgentThinking, updateAgentThinking } from "./api";

type UseAgentThinkingSettingsState = {
  thinking: Record<string, boolean>;
  draft: Record<string, boolean>;
  isLoading: boolean;
  isSaving: boolean;
  isDirty: boolean;
  statusMessage: string;
  errorMessage: string;
  refresh: () => Promise<void>;
  setDraftValue: (agentKey: string, nextValue: boolean) => void;
  reset: () => void;
  save: () => Promise<void>;
};

export function useAgentThinkingSettings(): UseAgentThinkingSettingsState {
  const [thinking, setThinking] = useState<Record<string, boolean>>({});
  const [draft, setDraft] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getAgentThinking();
      setThinking(data.thinking ?? {});
      setDraft(data.thinking ?? {});
    } catch (err) {
      setErrorMessage(formatApiError(err, "Failed to load agent thinking settings"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setDraftValue = useCallback((agentKey: string, nextValue: boolean) => {
    setDraft((prev) => ({ ...prev, [agentKey]: nextValue }));
  }, []);

  const reset = useCallback(() => {
    setDraft(thinking);
    setStatusMessage("");
    setErrorMessage("");
  }, [thinking]);

  const isDirty = Object.keys({ ...thinking, ...draft }).some(
    (key) => Boolean(thinking[key] ?? true) !== Boolean(draft[key] ?? true)
  );

  const save = useCallback(async () => {
    setIsSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const saved = await updateAgentThinking({ thinking: draft });
      setThinking(saved.thinking ?? {});
      setDraft(saved.thinking ?? {});
      setStatusMessage("Agent thinking settings saved");
    } catch (err) {
      setErrorMessage(formatApiError(err, "Failed to save agent thinking settings"));
    } finally {
      setIsSaving(false);
    }
  }, [draft]);

  return {
    thinking,
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
