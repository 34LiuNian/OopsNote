"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Button, Checkbox, Flash, Heading, Text } from "@primer/react";
import { GearIcon } from "@primer/octicons-react";
import { useTheme } from "../../components/ThemeProvider";
import { SettingsAppearanceSection } from "../../components/settings/SettingsAppearanceSection";
import { SettingsGatewaySection } from "../../components/settings/SettingsGatewaySection";
import { SettingsModelSection } from "../../components/settings/SettingsModelSection";
import { SettingsDebugSection } from "../../components/settings/SettingsDebugSection";
import { SettingsSystemInfoSection } from "../../components/settings/SettingsSystemInfoSection";
import {
  useAgentEnabledSettings,
  useAgentModelsSettings,
  useAgentTemperatureSettings,
  useAgentThinkingSettings,
  useDebugSettings,
  useGatewaySettings,
  useModelList,
  useSystemInfo,
} from "../../features/settings";
import { getRegistrationSettings, updateRegistrationSettings } from "../../features/auth/api";

const AGENTS: Array<{ key: string; label: string; description: string }> = [
  { key: "SOLVER", label: "Solver", description: "主解题与结构化输出" },
  { key: "TAGGER", label: "Tagger", description: "标签/知识点归类" },
  { key: "OCR", label: "OCR", description: "图片 OCR 与结构化题面提取" },
];

const LOCKED_ENABLED = new Set(["OCR", "SOLVER", "TAGGER"]);

export default function SettingsPage() {
  const { preference, resolvedTheme, setPreference } = useTheme();
  const didInitialLoadRef = useRef(false);

  // --- Agent Models ---
  const {
    agentModels,
    draft,
    isLoading: isLoadingSettings,
    isSaving,
    isDirty,
    statusMessage,
    errorMessage: agentModelsErrorMessage,
    refresh: refreshAgentModels,
    setDraftValue,
    reset: resetAgentModels,
    save: saveAgentModels,
  } = useAgentModelsSettings();

  // --- Agent Enabled ---
  const {
    enabled: agentEnabled,
    isLoading: isLoadingEnabled,
    savingAgent: savingEnabledAgent,
    statusMessage: enabledStatusMessage,
    errorMessage: enabledErrorMessage,
    refresh: refreshAgentEnabled,
    update: updateAgentEnabled,
  } = useAgentEnabledSettings({ lockedKeys: LOCKED_ENABLED });

  // --- Agent Thinking ---
  const {
    thinking: agentThinking,
    isLoading: isLoadingThinking,
    savingAgent: savingThinkingAgent,
    statusMessage: thinkingStatusMessage,
    errorMessage: thinkingErrorMessage,
    refresh: refreshAgentThinking,
    update: updateAgentThinking,
  } = useAgentThinkingSettings();

  // --- Agent Temperature ---
  const {
    temperature: agentTemperature,
    isLoading: isLoadingTemperature,
    savingAgent: savingTemperatureAgent,
    statusMessage: temperatureStatusMessage,
    errorMessage: temperatureErrorMessage,
    refresh: refreshAgentTemperature,
    update: updateAgentTemperature,
  } = useAgentTemperatureSettings();

  // --- Model List ---
  const {
    items: models,
    isLoading: isLoadingModels,
    errorMessage: modelsErrorMessage,
    refresh: refreshModels,
  } = useModelList();

  // --- Gateway ---
  const gateway = useGatewaySettings();

  // --- Debug ---
  const debug = useDebugSettings();

  // --- System Info ---
  const systemInfo = useSystemInfo();
  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  const [registrationLoaded, setRegistrationLoaded] = useState(false);
  const [registrationSaving, setRegistrationSaving] = useState(false);
  const [registrationError, setRegistrationError] = useState("");
  const [registrationStatus, setRegistrationStatus] = useState("");

  const sortedModels = useMemo(() => {
    return [...models].filter((m) => m?.id).sort((a, b) => a.id.localeCompare(b.id));
  }, [models]);

  useEffect(() => {
    if (didInitialLoadRef.current) return;
    didInitialLoadRef.current = true;

    void refreshAgentModels();
    void refreshModels(false);
    void refreshAgentEnabled();
    void refreshAgentThinking();
    void refreshAgentTemperature();
    void gateway.refresh();
    void debug.refresh();
    void systemInfo.refresh();
    void getRegistrationSettings()
      .then((value) => {
        setRegistrationEnabled(Boolean(value.enabled));
      })
      .catch((err) => {
        setRegistrationError(err instanceof Error ? err.message : "加载注册设置失败");
      })
      .finally(() => {
        setRegistrationLoaded(true);
      });
  }, [
    refreshAgentModels,
    refreshModels,
    refreshAgentEnabled,
    refreshAgentThinking,
    refreshAgentTemperature,
    gateway.refresh,
    debug.refresh,
    systemInfo.refresh,
  ]);

  const handleSaveRegistration = useCallback(async () => {
    setRegistrationError("");
    setRegistrationStatus("");
    setRegistrationSaving(true);
    try {
      const next = await updateRegistrationSettings({ enabled: registrationEnabled });
      setRegistrationEnabled(Boolean(next.enabled));
      setRegistrationStatus("注册开关已更新");
    } catch (err) {
      setRegistrationError(err instanceof Error ? err.message : "保存注册设置失败");
    } finally {
      setRegistrationSaving(false);
    }
  }, [registrationEnabled]);

  const handleEnabledChange = useCallback(
    async (agentKey: string, nextValue: boolean) => {
      if ((agentEnabled[agentKey] ?? true) === nextValue) return;
      await updateAgentEnabled(agentKey, nextValue);
    },
    [updateAgentEnabled]
  );

  const handleThinkingChange = useCallback(
    async (agentKey: string, nextValue: boolean) => {
      if ((agentThinking[agentKey] ?? true) === nextValue) return;
      await updateAgentThinking(agentKey, nextValue);
    },
    [updateAgentThinking]
  );

  const handleTemperatureChange = useCallback(
    async (agentKey: string, value: number | null) => {
      await updateAgentTemperature(agentKey, value);
    },
    [updateAgentTemperature]
  );

  const handleChange = (agentKey: string, value: string) => {
    setDraftValue(agentKey, value);
  };

  const handleReset = useCallback(() => {
    resetAgentModels();
  }, [resetAgentModels]);

  const handleSave = useCallback(async () => {
    await saveAgentModels();
  }, [saveAgentModels]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {/* Page header */}
      <Box className="oops-section-header" sx={{ border: "none !important", mb: 0, pb: 2 }}>
        <GearIcon size={20} />
        <Box sx={{ flex: 1 }}>
          <Text className="oops-section-subtitle">Settings</Text>
          <Heading as="h2" className="oops-section-title" sx={{ m: 0 }}>
            设置
          </Heading>
        </Box>
      </Box>

      {/* 1. Appearance */}
      <SettingsAppearanceSection
        preference={preference}
        resolvedTheme={resolvedTheme}
        onChangePreference={setPreference}
      />

      {/* 2. Gateway / Connection */}
      <SettingsGatewaySection
        saved={gateway.saved}
        draft={gateway.draft}
        isDirty={gateway.isDirty}
        isLoading={gateway.isLoading}
        isSaving={gateway.isSaving}
        isTesting={gateway.isTesting}
        testResult={gateway.testResult}
        statusMessage={gateway.statusMessage}
        errorMessage={gateway.errorMessage}
        onSetDraftField={gateway.setDraftField}
        onReset={gateway.reset}
        onSave={gateway.save}
        onTest={gateway.test}
      />

      <Box className="oops-card" sx={{ p: 3, display: "grid", gap: 3 }}>
        <Box>
          <Heading as="h3" sx={{ fontSize: 2, mb: 1 }}>
            账号注册
          </Heading>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>
            控制登录页是否允许用户自助注册。
          </Text>
        </Box>
        {!registrationLoaded ? <Text sx={{ color: "fg.muted" }}>加载中...</Text> : null}
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Checkbox
            checked={registrationEnabled}
            onChange={(event) => setRegistrationEnabled(event.target.checked)}
          />
          <Text>开放自助注册</Text>
        </Box>
        {registrationError ? <Flash variant="danger">{registrationError}</Flash> : null}
        {registrationStatus ? <Flash variant="success">{registrationStatus}</Flash> : null}
        <Box>
          <Button variant="primary" onClick={() => void handleSaveRegistration()} disabled={registrationSaving}>
            {registrationSaving ? "保存中..." : "保存注册设置"}
          </Button>
        </Box>
      </Box>

      {/* 3. Model Settings */}
      <SettingsModelSection
        agents={AGENTS}
        sortedModels={sortedModels}
        draft={draft}
        agentModels={agentModels}
        lockedEnabled={LOCKED_ENABLED}
        agentEnabled={agentEnabled}
        agentThinking={agentThinking}
        agentTemperature={agentTemperature}
        isDirty={isDirty}
        isSaving={isSaving}
        isLoadingSettings={isLoadingSettings}
        isLoadingModels={isLoadingModels}
        isLoadingEnabled={isLoadingEnabled}
        isLoadingThinking={isLoadingThinking}
        savingEnabledAgent={savingEnabledAgent}
        savingThinkingAgent={savingThinkingAgent}
        savingTemperatureAgent={savingTemperatureAgent}
        statusMessage={statusMessage}
        agentModelsErrorMessage={agentModelsErrorMessage}
        modelsErrorMessage={modelsErrorMessage}
        enabledStatusMessage={enabledStatusMessage}
        enabledErrorMessage={enabledErrorMessage}
        thinkingStatusMessage={thinkingStatusMessage}
        thinkingErrorMessage={thinkingErrorMessage}
        temperatureErrorMessage={temperatureErrorMessage}
        onRefreshModels={refreshModels}
        onReset={handleReset}
        onSave={handleSave}
        onChangeModel={handleChange}
        onToggleEnabled={handleEnabledChange}
        onToggleThinking={handleThinkingChange}
        onChangeTemperature={handleTemperatureChange}
      />

      {/* 4. Debug */}
      <SettingsDebugSection
        settings={debug.settings}
        isLoading={debug.isLoading}
        isSaving={debug.isSaving}
        statusMessage={debug.statusMessage}
        errorMessage={debug.errorMessage}
        onToggle={debug.toggle}
      />

      {/* 5. System Info */}
      <SettingsSystemInfoSection
        info={systemInfo.info}
        isLoading={systemInfo.isLoading}
        errorMessage={systemInfo.errorMessage}
      />
    </Box>
  );
}
