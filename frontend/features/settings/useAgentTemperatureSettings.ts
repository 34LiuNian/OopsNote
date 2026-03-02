"use client";

import { useCallback, useState } from "react";
import { formatApiError } from "./errors";
import { getAgentTemperature, updateAgentTemperature } from "./api";

type UseAgentTemperatureSettingsState = {
  temperature: Record<string, number>;
  isLoading: boolean;
  savingAgent: string | null;
  statusMessage: string;
  errorMessage: string;
  refresh: () => Promise<void>;
  update: (agentKey: string, value: number | null) => Promise<void>;
};

export function useAgentTemperatureSettings(): UseAgentTemperatureSettingsState {
  const [temperature, setTemperature] = useState<Record<string, number>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [savingAgent, setSavingAgent] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getAgentTemperature();
      setTemperature(data.temperature ?? {});
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载温度设置失败"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const update = useCallback(
    async (agentKey: string, value: number | null) => {
      setSavingAgent(agentKey);
      setErrorMessage("");
      setStatusMessage("");

      const next = { ...temperature };
      if (value === null) {
        delete next[agentKey];
      } else {
        next[agentKey] = value;
      }

      try {
        const saved = await updateAgentTemperature({ temperature: next });
        setTemperature(saved.temperature ?? {});
        setStatusMessage("已更新温度设置。");
      } catch (err) {
        setErrorMessage(formatApiError(err, "更新温度失败"));
      } finally {
        setSavingAgent(null);
      }
    },
    [temperature]
  );

  return {
    temperature,
    isLoading,
    savingAgent,
    statusMessage,
    errorMessage,
    refresh,
    update,
  };
}
