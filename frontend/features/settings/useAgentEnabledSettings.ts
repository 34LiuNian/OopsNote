"use client";

import { useCallback, useState } from "react";
import { formatApiError } from "./errors";
import { getAgentEnabled, updateAgentEnabled } from "./api";

type UseAgentEnabledSettingsState = {
  enabled: Record<string, boolean>;
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

type UseAgentEnabledSettingsOptions = {
  lockedKeys?: Set<string>;
};

function applyLockedKeys(
  value: Record<string, boolean>,
  lockedKeys: Set<string>
): Record<string, boolean> {
  const next = { ...value };
  for (const key of lockedKeys) {
    next[key] = true;
  }
  return next;
}

export function useAgentEnabledSettings(
  options: UseAgentEnabledSettingsOptions = {}
): UseAgentEnabledSettingsState {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [draft, setDraft] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const lockedKeys = options.lockedKeys ?? new Set<string>();

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getAgentEnabled();
      const next = applyLockedKeys(data.enabled ?? {}, lockedKeys);
      setEnabled(next);
      setDraft(next);
    } catch (err) {
      setErrorMessage(formatApiError(err, "Failed to load agent enabled settings"));
    } finally {
      setIsLoading(false);
    }
  }, [lockedKeys]);

  const setDraftValue = useCallback(
    (agentKey: string, nextValue: boolean) => {
      setDraft((prev) => applyLockedKeys({ ...prev, [agentKey]: nextValue }, lockedKeys));
    },
    [lockedKeys]
  );

  const reset = useCallback(() => {
    setDraft(enabled);
    setStatusMessage("");
    setErrorMessage("");
  }, [enabled]);

  const isDirty = Object.keys({ ...enabled, ...draft }).some(
    (key) => Boolean(enabled[key] ?? true) !== Boolean(draft[key] ?? true)
  );

  const save = useCallback(async () => {
    setIsSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const saved = await updateAgentEnabled({ enabled: applyLockedKeys(draft, lockedKeys) });
      const next = applyLockedKeys(saved.enabled ?? {}, lockedKeys);
      setEnabled(next);
      setDraft(next);
      setStatusMessage("Agent enabled settings saved");
    } catch (err) {
      setErrorMessage(formatApiError(err, "Failed to save agent enabled settings"));
    } finally {
      setIsSaving(false);
    }
  }, [draft, lockedKeys]);

  return {
    enabled,
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
