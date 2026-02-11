"use client";

import { useCallback, useState } from "react";
import { formatApiError } from "./errors";
import { getAgentEnabled, updateAgentEnabled } from "./api";

type UseAgentEnabledSettingsState = {
  enabled: Record<string, boolean>;
  isLoading: boolean;
  savingAgent: string | null;
  statusMessage: string;
  errorMessage: string;
  refresh: () => Promise<void>;
  update: (agentKey: string, nextValue: boolean) => Promise<void>;
};

type UseAgentEnabledSettingsOptions = {
  lockedKeys?: Set<string>;
};

export function useAgentEnabledSettings(
  options: UseAgentEnabledSettingsOptions = {}
): UseAgentEnabledSettingsState {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [savingAgent, setSavingAgent] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const lockedKeys = options.lockedKeys ?? new Set<string>();

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getAgentEnabled();
      setEnabled(data.enabled ?? {});
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载 agent 开关失败"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const update = useCallback(
    async (agentKey: string, nextValue: boolean) => {
      if ((enabled[agentKey] ?? true) === nextValue) return;

      setSavingAgent(agentKey);
      setErrorMessage("");
      setStatusMessage("");

      const next = { ...enabled, [agentKey]: nextValue };
      for (const key of lockedKeys) {
        next[key] = true;
      }

      try {
        const saved = await updateAgentEnabled({ enabled: next });
        setEnabled(saved.enabled ?? {});
        setStatusMessage("已更新 agent 开关。 ");
      } catch (err) {
        setErrorMessage(formatApiError(err, "更新失败"));
      } finally {
        setSavingAgent(null);
      }
    },
    [enabled, lockedKeys]
  );

  return {
    enabled,
    isLoading,
    savingAgent,
    statusMessage,
    errorMessage,
    refresh,
    update,
  };
}
