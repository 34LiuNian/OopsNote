"use client";

import { useCallback, useMemo, useState } from "react";
import { formatApiError } from "./errors";
import { getAgentTemperature, updateAgentTemperature } from "./api";

type UseAgentTemperatureSettingsState = {
  temperature: Record<string, number>;
  draft: Record<string, string>;
  isLoading: boolean;
  isSaving: boolean;
  isDirty: boolean;
  statusMessage: string;
  errorMessage: string;
  refresh: () => Promise<void>;
  setDraftValue: (agentKey: string, value: string) => void;
  reset: () => void;
  save: () => Promise<void>;
};

function toDraft(value: Record<string, number>): Record<string, string> {
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item)]));
}

function normalizeDraft(value: Record<string, string>): Record<string, number> {
  const next: Record<string, number> = {};
  for (const [key, rawValue] of Object.entries(value)) {
    const trimmed = rawValue.trim();
    if (!trimmed) continue;
    const parsed = parseFloat(trimmed);
    if (!Number.isNaN(parsed)) {
      next[key] = parsed;
    }
  }
  return next;
}

export function useAgentTemperatureSettings(): UseAgentTemperatureSettingsState {
  const [temperature, setTemperature] = useState<Record<string, number>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getAgentTemperature();
      const next = data.temperature ?? {};
      setTemperature(next);
      setDraft(toDraft(next));
    } catch (err) {
      setErrorMessage(formatApiError(err, "Failed to load agent temperature settings"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setDraftValue = useCallback((agentKey: string, value: string) => {
    setDraft((prev) => {
      const next = { ...prev };
      if (value.trim()) {
        next[agentKey] = value;
      } else {
        delete next[agentKey];
      }
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setDraft(toDraft(temperature));
    setStatusMessage("");
    setErrorMessage("");
  }, [temperature]);

  const savedDraft = useMemo(() => toDraft(temperature), [temperature]);
  const isDirty = Object.keys({ ...savedDraft, ...draft }).some(
    (key) => (savedDraft[key] ?? "") !== (draft[key] ?? "")
  );

  const save = useCallback(async () => {
    setIsSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const saved = await updateAgentTemperature({ temperature: normalizeDraft(draft) });
      const next = saved.temperature ?? {};
      setTemperature(next);
      setDraft(toDraft(next));
      setStatusMessage("Agent temperature settings saved");
    } catch (err) {
      setErrorMessage(formatApiError(err, "Failed to save agent temperature settings"));
    } finally {
      setIsSaving(false);
    }
  }, [draft]);

  return {
    temperature,
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
