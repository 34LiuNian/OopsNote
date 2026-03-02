"use client";

import { useCallback, useState } from "react";
import { formatApiError } from "./errors";
import {
  getGatewaySettings,
  updateGatewaySettings,
  testGatewayConnection,
} from "./api";
import type {
  GatewaySettingsResponse,
  GatewayTestResponse,
} from "../../types/api";

type GatewayDraft = {
  base_url: string;
  api_key: string;
  default_model: string;
  temperature: string;
};

function responseToDraft(data: GatewaySettingsResponse): GatewayDraft {
  return {
    base_url: data.base_url ?? "",
    api_key: "",
    default_model: data.default_model ?? "",
    temperature: data.temperature != null ? String(data.temperature) : "",
  };
}

type UseGatewaySettingsState = {
  saved: GatewaySettingsResponse | null;
  draft: GatewayDraft;
  isDirty: boolean;
  isLoading: boolean;
  isSaving: boolean;
  isTesting: boolean;
  testResult: GatewayTestResponse | null;
  statusMessage: string;
  errorMessage: string;
  refresh: () => Promise<void>;
  setDraftField: (field: keyof GatewayDraft, value: string) => void;
  reset: () => void;
  save: () => Promise<void>;
  test: () => Promise<void>;
};

const EMPTY_DRAFT: GatewayDraft = {
  base_url: "",
  api_key: "",
  default_model: "",
  temperature: "",
};

export function useGatewaySettings(): UseGatewaySettingsState {
  const [saved, setSaved] = useState<GatewaySettingsResponse | null>(null);
  const [draft, setDraft] = useState<GatewayDraft>(EMPTY_DRAFT);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<GatewayTestResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getGatewaySettings();
      setSaved(data);
      setDraft(responseToDraft(data));
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载连接配置失败"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setDraftField = useCallback(
    (field: keyof GatewayDraft, value: string) => {
      setDraft((prev) => ({ ...prev, [field]: value }));
    },
    []
  );

  const reset = useCallback(() => {
    if (saved) setDraft(responseToDraft(saved));
  }, [saved]);

  const isDirty =
    saved != null &&
    (draft.base_url !== (saved.base_url ?? "") ||
      draft.api_key !== "" ||
      draft.default_model !== (saved.default_model ?? "") ||
      draft.temperature !== (saved.temperature != null ? String(saved.temperature) : ""));

  const save = useCallback(async () => {
    setIsSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const temp = draft.temperature ? parseFloat(draft.temperature) : undefined;
      const data = await updateGatewaySettings({
        base_url: draft.base_url || undefined,
        api_key: draft.api_key || "__UNCHANGED__",
        default_model: draft.default_model || undefined,
        temperature: !isNaN(temp as number) ? temp : undefined,
      });
      setSaved(data);
      setDraft(responseToDraft(data));
      setStatusMessage("连接配置已保存。");
    } catch (err) {
      setErrorMessage(formatApiError(err, "保存连接配置失败"));
    } finally {
      setIsSaving(false);
    }
  }, [draft]);

  const test = useCallback(async () => {
    const targetUrl = draft.base_url || saved?.env_base_url;
    if (!targetUrl) {
      setTestResult({ success: false, message: "未配置 Base URL", models_count: 0 });
      return;
    }
    setIsTesting(true);
    setTestResult(null);
    try {
      const apiKey = draft.api_key || undefined;
      const result = await testGatewayConnection({
        base_url: targetUrl,
        api_key: apiKey,
      });
      setTestResult(result);
    } catch (err) {
      setTestResult({
        success: false,
        message: formatApiError(err, "测试失败"),
        models_count: 0,
      });
    } finally {
      setIsTesting(false);
    }
  }, [draft, saved]);

  return {
    saved,
    draft,
    isDirty,
    isLoading,
    isSaving,
    isTesting,
    testResult,
    statusMessage,
    errorMessage,
    refresh,
    setDraftField,
    reset,
    save,
    test,
  };
}
