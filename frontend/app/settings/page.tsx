"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { 
  Box, 
  Heading, 
  Text, 
  Select, 
  Button, 
  ToggleSwitch,
  FormControl, 
  Flash, 
  Label,
  Spinner
} from "@primer/react";
import { SyncIcon } from "@primer/octicons-react";
import { fetchJson } from "../../lib/api";
import { useTheme } from "../../components/ThemeProvider";
import type {
  AgentModelsResponse,
  AgentModelsUpdateRequest,
  AgentEnabledResponse,
  AgentEnabledUpdateRequest,
  AgentThinkingResponse,
  AgentThinkingUpdateRequest,
  ModelsResponse,
} from "../../types/api";

const AGENTS: Array<{ key: string; label: string; description: string }> = [
  { key: "SOLVER", label: "Solver", description: "主解题与结构化输出" },
  { key: "TAGGER", label: "Tagger", description: "标签/知识点归类" },
  { key: "OCR", label: "OCR", description: "图片 OCR 与结构化题面提取" },
];

const LOCKED_ENABLED = new Set(["OCR", "SOLVER", "TAGGER"]);

function formatApiError(err: unknown, fallback: string) {
  if (!(err instanceof Error)) return fallback;
  const text = err.message?.trim();
  if (!text) return fallback;

  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    }
  } catch {
    // ignore JSON parse errors
  }

  return text;
}

export default function SettingsPage() {
  const { preference, resolvedTheme, setPreference } = useTheme();
  const didInitialLoadRef = useRef(false);
  const [models, setModels] = useState<ModelsResponse["items"]>([]);
  const [agentModels, setAgentModels] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});

  const [agentEnabled, setAgentEnabled] = useState<Record<string, boolean>>({});
  const [isLoadingEnabled, setIsLoadingEnabled] = useState(false);
  const [savingEnabledAgent, setSavingEnabledAgent] = useState<string | null>(null);
  const [enabledStatusMessage, setEnabledStatusMessage] = useState<string>("");
  const [enabledErrorMessage, setEnabledErrorMessage] = useState<string>("");

  const [agentThinking, setAgentThinking] = useState<Record<string, boolean>>({});
  const [isLoadingThinking, setIsLoadingThinking] = useState(false);
  const [savingThinkingAgent, setSavingThinkingAgent] = useState<string | null>(null);
  const [thinkingStatusMessage, setThinkingStatusMessage] = useState<string>("");
  const [thinkingErrorMessage, setThinkingErrorMessage] = useState<string>("");

  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [isLoadingSettings, setIsLoadingSettings] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const [statusMessage, setStatusMessage] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string>("");

  const sortedModels = useMemo(() => {
    return [...models].filter((m) => m?.id).sort((a, b) => a.id.localeCompare(b.id));
  }, [models]);

  const normalizeModelsMap = useCallback((value: Record<string, string>) => {
    const entries = Object.entries(value).filter(([, v]) => typeof v === "string" && v.trim());
    return Object.fromEntries(entries);
  }, []);

  const normalizedDraft = useMemo(() => normalizeModelsMap(draft), [draft, normalizeModelsMap]);
  const normalizedSaved = useMemo(() => normalizeModelsMap(agentModels), [agentModels, normalizeModelsMap]);

  const isDirty = useMemo(() => {
    const a = normalizedDraft;
    const b = normalizedSaved;
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of keys) {
      if ((a[k] ?? "") !== (b[k] ?? "")) return true;
    }
    return false;
  }, [normalizedDraft, normalizedSaved]);

  const loadAgentModels = useCallback(async () => {
    setIsLoadingSettings(true);
    setErrorMessage("");
    try {
      const data = await fetchJson<AgentModelsResponse>("/settings/agent-models");
      setAgentModels(data.models ?? {});
      setDraft(data.models ?? {});
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载 agent 模型设置失败"));
    } finally {
      setIsLoadingSettings(false);
    }
  }, []);

  const loadAgentEnabled = useCallback(async () => {
    setIsLoadingEnabled(true);
    setEnabledErrorMessage("");
    try {
      const data = await fetchJson<AgentEnabledResponse>("/settings/agent-enabled");
      setAgentEnabled(data.enabled ?? {});
    } catch (err) {
      setEnabledErrorMessage(formatApiError(err, "加载 agent 开关失败"));
    } finally {
      setIsLoadingEnabled(false);
    }
  }, []);

  const loadAgentThinking = useCallback(async () => {
    setIsLoadingThinking(true);
    setThinkingErrorMessage("");
    try {
      const data = await fetchJson<AgentThinkingResponse>("/settings/agent-thinking");
      setAgentThinking(data.thinking ?? {});
    } catch (err) {
      setThinkingErrorMessage(formatApiError(err, "加载思考开关失败"));
    } finally {
      setIsLoadingThinking(false);
    }
  }, []);

  const loadModels = useCallback(async (refresh: boolean) => {
    setIsLoadingModels(true);
    setErrorMessage("");
    try {
      const query = refresh ? "?refresh=true" : "";
      const data = await fetchJson<ModelsResponse>(`/models${query}`);
      setModels(data.items ?? []);
    } catch (err) {
      setErrorMessage(formatApiError(err, "加载模型列表失败"));
    } finally {
      setIsLoadingModels(false);
    }
  }, []);

  useEffect(() => {
    // Guard against Next.js dev StrictMode double-invocation / accidental remount loops.
    if (didInitialLoadRef.current) return;
    didInitialLoadRef.current = true;

    void loadAgentModels();
    void loadModels(false);
    void loadAgentEnabled();
    void loadAgentThinking();
  }, [loadAgentModels, loadModels, loadAgentEnabled, loadAgentThinking]);

  const handleEnabledChange = useCallback(
    async (agentKey: string, nextValue: boolean) => {
      if ((agentEnabled[agentKey] ?? true) === nextValue) return;

      setSavingEnabledAgent(agentKey);
      setEnabledErrorMessage("");
      setEnabledStatusMessage("");

      const next = { ...agentEnabled, [agentKey]: nextValue };

      // Enforce locked agents on client side too.
      for (const key of LOCKED_ENABLED) {
        next[key] = true;
      }

      try {
        const payload: AgentEnabledUpdateRequest = { enabled: next };
        const saved = await fetchJson<AgentEnabledResponse>("/settings/agent-enabled", {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setAgentEnabled(saved.enabled ?? {});
        setEnabledStatusMessage("已更新 agent 开关。");
      } catch (err) {
        setEnabledErrorMessage(formatApiError(err, "更新失败"));
      } finally {
        setSavingEnabledAgent(null);
      }
    },
    [agentEnabled]
  );

  const handleThinkingChange = useCallback(
    async (agentKey: string, nextValue: boolean) => {
      if ((agentThinking[agentKey] ?? true) === nextValue) return;

      setSavingThinkingAgent(agentKey);
      setThinkingErrorMessage("");
      setThinkingStatusMessage("");

      const next = { ...agentThinking, [agentKey]: nextValue };

      try {
        const payload: AgentThinkingUpdateRequest = { thinking: next };
        const saved = await fetchJson<AgentThinkingResponse>("/settings/agent-thinking", {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setAgentThinking(saved.thinking ?? {});
        setThinkingStatusMessage("已更新思考开关。 ");
      } catch (err) {
        setThinkingErrorMessage(formatApiError(err, "更新失败"));
      } finally {
        setSavingThinkingAgent(null);
      }
    },
    [agentThinking]
  );

  const handleChange = (agentKey: string, value: string) => {
    setDraft((prev) => {
      const next = { ...prev };
      if (!value) {
        delete next[agentKey];
      } else {
        next[agentKey] = value;
      }
      return next;
    });
  };

  const handleReset = useCallback(() => {
    setDraft(agentModels ?? {});
    setStatusMessage("");
    setErrorMessage("");
  }, [agentModels]);

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const payload: AgentModelsUpdateRequest = {
        models: normalizedDraft,
      };
      const saved = await fetchJson<AgentModelsResponse>("/settings/agent-models", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setAgentModels(saved.models ?? {});
      setDraft(saved.models ?? {});
      setStatusMessage("已保存：下次调用会按 agent 覆盖模型。");
    } catch (err) {
      setErrorMessage(formatApiError(err, "保存失败"));
    } finally {
      setIsSaving(false);
    }
  }, [normalizedDraft]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {/* Appearance */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
        <Box sx={{ mb: 3 }}>
          <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Appearance</Text>
          <Heading as="h2" sx={{ fontSize: 3 }}>外观</Heading>
        </Box>

        <FormControl>
          <FormControl.Label>主题</FormControl.Label>
          <Select 
            value={preference} 
            onChange={(e) => setPreference(e.target.value as "system" | "light" | "dark")}
            block
          >
            <Select.Option value="system">跟随系统（当前：{resolvedTheme === "dark" ? "暗色" : "亮色"}）</Select.Option>
            <Select.Option value="light">亮色</Select.Option>
            <Select.Option value="dark">暗色</Select.Option>
          </Select>
          <FormControl.Caption>选择“跟随系统”会在系统主题变化时自动切换。</FormControl.Caption>
        </FormControl>
      </Box>

      {/* Model Settings */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Settings</Text>
            <Heading as="h2" sx={{ fontSize: 3 }}>模型设置</Heading>
          </Box>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button 
              onClick={() => loadModels(true)} 
              disabled={isLoadingModels || isSaving}
              leadingVisual={SyncIcon}
            >
              {isLoadingModels ? "刷新中..." : "刷新模型列表"}
            </Button>
            <Button 
              onClick={handleReset} 
              disabled={!isDirty || isSaving || isLoadingSettings}
            >
              重置
            </Button>
            <Button 
              variant="primary"
              onClick={handleSave} 
              disabled={!isDirty || isSaving || isLoadingSettings}
            >
              {isSaving ? "保存中..." : "保存"}
            </Button>
          </Box>
        </Box>

        {isDirty && !isSaving && !isLoadingSettings && (
          <Label variant="attention" sx={{ mb: 3, display: 'inline-block' }}>有未保存更改</Label>
        )}
        {statusMessage && <Flash variant="success" sx={{ mb: 3 }}>{statusMessage}</Flash>}
        {errorMessage && <Flash variant="danger" sx={{ mb: 3 }}>{errorMessage}</Flash>}
        {enabledStatusMessage && <Flash variant="success" sx={{ mb: 3 }}>{enabledStatusMessage}</Flash>}
        {enabledErrorMessage && <Flash variant="danger" sx={{ mb: 3 }}>{enabledErrorMessage}</Flash>}
        {thinkingStatusMessage && <Flash variant="success" sx={{ mb: 3 }}>{thinkingStatusMessage}</Flash>}
        {thinkingErrorMessage && <Flash variant="danger" sx={{ mb: 3 }}>{thinkingErrorMessage}</Flash>}

        <Box sx={{ p: 3, bg: 'canvas.subtle', borderRadius: 2, mb: 4 }}>
          <Text as="p" sx={{ mb: 1 }}>
            说明：模型列表来自后端的 <strong>/models</strong>（会转发到 OpenAI 兼容网关的 <strong>/v1/models</strong>）。
          </Text>
          <Text as="p" sx={{ fontSize: 1, color: 'fg.muted' }}>
            如果提示缺少配置，请先在后端设置 <strong>OPENAI_BASE_URL</strong>（例如 http://127.0.0.1:23333/v1）和
            <strong>OPENAI_API_KEY</strong>，或在 agent TOML 配置里填写 default.base_url/default.api_key。
          </Text>
        </Box>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {AGENTS.map((agent) => {
            const currentValue = draft[agent.key] ?? "";
            const hasCurrentInList = currentValue
              ? sortedModels.some((m) => m.id === currentValue)
              : true;

            const locked = LOCKED_ENABLED.has(agent.key);
            const enabled = locked ? true : Boolean(agentEnabled[agent.key] ?? true);
            const isThisSaving = savingEnabledAgent === agent.key;
            const thinkingEnabled = Boolean(agentThinking[agent.key] ?? true);
            const isThisThinkingSaving = savingThinkingAgent === agent.key;
            const isControlBusy = isLoadingEnabled || isThisSaving || isLoadingThinking || isThisThinkingSaving;

            return (
              <Box
                key={agent.key}
                sx={{
                  display: 'grid',
                  gridTemplateColumns: ['1fr', '1fr 1fr auto'],
                  gap: 3,
                  alignItems: 'start',
                  p: 2,
                  borderBottom: '1px solid',
                  borderColor: 'border.muted',
                }}
              >
                <Box>
                  <Text sx={{ fontWeight: 'bold', display: 'block' }}>[{agent.label}] 模型</Text>
                  <Text sx={{ fontSize: 1, color: 'fg.muted' }}>{agent.description}</Text>
                </Box>

                <FormControl>
                  <FormControl.Label visuallyHidden>模型</FormControl.Label>
                  <Select
                    value={currentValue}
                    onChange={(e) => handleChange(agent.key, e.target.value)}
                    // Allow clearing overrides even if model list is empty.
                    disabled={isLoadingSettings || isSaving || isLoadingModels}
                    block
                  >
                    <Select.Option value="">默认（不覆盖）</Select.Option>
                    {!hasCurrentInList && (
                      <Select.Option value={currentValue}>{currentValue}（当前）</Select.Option>
                    )}
                    {sortedModels.length === 0 && (
                      <Select.Option value="" disabled>
                        {isLoadingModels ? "模型列表加载中..." : "模型列表为空（请先配置网关）"}
                      </Select.Option>
                    )}
                    {sortedModels.map((m) => (
                      <Select.Option key={m.id} value={m.id}>
                        {m.id}
                      </Select.Option>
                    ))}
                  </Select>
                </FormControl>

                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2, pt: [0, 1] }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Text sx={{ fontSize: 1, color: locked ? 'fg.muted' : 'fg.default' }}>
                      {locked ? '必开' : '启用'}
                    </Text>
                    <ToggleSwitch
                      size="small"
                      checked={enabled}
                      disabled={locked || isControlBusy}
                      // Primer ToggleSwitch renders an On/Off status label and inner icons.
                      // Hide both for a cleaner GitHub-like settings switch (track + knob only).
                      sx={{
                        '& > span[aria-hidden="true"]': { display: 'none' },
                        '& button svg': { display: 'none' },
                      }}
                      onChange={(next: unknown) => {
                        if (locked) return;
                        const nextChecked =
                          typeof next === "boolean"
                            ? next
                            : Boolean((next as { target?: { checked?: unknown } })?.target?.checked);
                        void handleEnabledChange(agent.key, nextChecked);
                      }}
                      aria-label={`${agent.label} 启用`}
                    />
                    {isThisSaving && <Spinner size="small" />}
                  </Box>

                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Text sx={{ fontSize: 1, color: 'fg.default' }}>思考</Text>
                    <ToggleSwitch
                      size="small"
                      checked={thinkingEnabled}
                      disabled={isControlBusy}
                      // Primer ToggleSwitch renders an On/Off status label and inner icons.
                      // Hide both for a cleaner GitHub-like settings switch (track + knob only).
                      sx={{
                        '& > span[aria-hidden="true"]': { display: 'none' },
                        '& button svg': { display: 'none' },
                      }}
                      onChange={(next: unknown) => {
                        const nextChecked =
                          typeof next === "boolean"
                            ? next
                            : Boolean((next as { target?: { checked?: unknown } })?.target?.checked);
                        void handleThinkingChange(agent.key, nextChecked);
                      }}
                      aria-label={`${agent.label} 思考`}
                    />
                    {isThisThinkingSaving && <Spinner size="small" />}
                  </Box>
                </Box>
              </Box>
            );
          })}
        </Box>

        <Text as="p" sx={{ fontSize: 1, color: 'fg.muted', mt: 3 }}>
          当前已保存覆盖：
          {Object.keys(agentModels).length === 0
            ? "无（全部使用默认模型）"
            : AGENTS.map((a) => {
                const v = agentModels[a.key];
                return v ? `${a.key}=${v}` : null;
              })
                .filter(Boolean)
                .join(" · ")}
        </Text>

        <Box sx={{ mt: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
          {(isLoadingEnabled || Boolean(savingEnabledAgent) || isLoadingThinking || Boolean(savingThinkingAgent)) && (
            <Spinner size="small" />
          )}
          <Text sx={{ fontSize: 1, color: 'fg.muted' }}>
            {isLoadingEnabled
              ? "加载开关中..."
              : savingEnabledAgent
                ? "保存开关中..."
                : isLoadingThinking
                  ? "加载思考开关中..."
                  : savingThinkingAgent
                    ? "保存思考开关中..."
                    : ""}
          </Text>
        </Box>
      </Box>
    </Box>
  );
}
