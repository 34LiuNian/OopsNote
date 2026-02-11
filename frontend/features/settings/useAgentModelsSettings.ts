"use client";

import { useCallback, useMemo, useState } from "react";
import { formatApiError } from "./errors";
import { getAgentModels, updateAgentModels } from "./api";

type UseAgentModelsSettingsState = {
  agentModels: Record<string, string>;
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

function normalizeModelsMap(value: Record<string, string>) {
  const entries = Object.entries(value).filter(([, v]) => typeof v === "string" && v.trim());
  return Object.fromEntries(entries);
}

export function useAgentModelsSettings(): UseAgentModelsSettingsState {
  const [agentModels, setAgentModels] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const normalizedDraft = useMemo(() => normalizeModelsMap(draft), [draft]);
  const normalizedSaved = useMemo(() => normalizeModelsMap(agentModels), [agentModels]);

  const isDirty = useMemo(() => {
    const a = normalizedDraft;
    const b = normalizedSaved;
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of keys) {
      if ((a[k] ?? "") !== (b[k] ?? "")) return true;
    }
    return false;
  }, [normalizedDraft, normalizedSaved]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getAgentModels();
      setAgentModels(data.models ?? {});
      setDraft(data.models ?? {});
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载 agent 模型设置失败"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setDraftValue = useCallback((agentKey: string, value: string) => {
    setDraft((prev) => {
      const next = { ...prev };
      if (!value) {
        delete next[agentKey];
      } else {
        next[agentKey] = value;
      }
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setDraft(agentModels ?? {});
    setStatusMessage("");
    setErrorMessage("");
  }, [agentModels]);

  const save = useCallback(async () => {
    setIsSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const saved = await updateAgentModels({ models: normalizedDraft });
      setAgentModels(saved.models ?? {});
      setDraft(saved.models ?? {});
      setStatusMessage("已保存：下次调用会按 agent 覆盖模型。");
    } catch (err) {
      setErrorMessage(formatApiError(err, "保存失败"));
    } finally {
      setIsSaving(false);
    }
  }, [normalizedDraft]);

  return {
    agentModels,
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
