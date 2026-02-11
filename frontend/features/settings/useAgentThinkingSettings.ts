"use client";

import { useCallback, useState } from "react";
import { formatApiError } from "./errors";
import { getAgentThinking, updateAgentThinking } from "./api";

type UseAgentThinkingSettingsState = {
  thinking: Record<string, boolean>;
  isLoading: boolean;
  savingAgent: string | null;
  statusMessage: string;
  errorMessage: string;
  refresh: () => Promise<void>;
  update: (agentKey: string, nextValue: boolean) => Promise<void>;
};

export function useAgentThinkingSettings(): UseAgentThinkingSettingsState {
  const [thinking, setThinking] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [savingAgent, setSavingAgent] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getAgentThinking();
      setThinking(data.thinking ?? {});
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载思考开关失败"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const update = useCallback(
    async (agentKey: string, nextValue: boolean) => {
      if ((thinking[agentKey] ?? true) === nextValue) return;

      setSavingAgent(agentKey);
      setErrorMessage("");
      setStatusMessage("");

      const next = { ...thinking, [agentKey]: nextValue };

      try {
        const saved = await updateAgentThinking({ thinking: next });
        setThinking(saved.thinking ?? {});
        setStatusMessage("已更新思考开关。 ");
      } catch (err) {
        setErrorMessage(formatApiError(err, "更新失败"));
      } finally {
        setSavingAgent(null);
      }
    },
    [thinking]
  );

  return {
    thinking,
    isLoading,
    savingAgent,
    statusMessage,
    errorMessage,
    refresh,
    update,
  };
}
