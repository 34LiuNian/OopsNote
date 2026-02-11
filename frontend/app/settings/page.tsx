"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { Box } from "@primer/react";
import { useTheme } from "../../components/ThemeProvider";
import { SettingsAppearanceSection } from "../../components/settings/SettingsAppearanceSection";
import { SettingsModelSection } from "../../components/settings/SettingsModelSection";
import {
  useAgentEnabledSettings,
  useAgentModelsSettings,
  useAgentThinkingSettings,
  useModelList,
} from "../../features/settings";

const AGENTS: Array<{ key: string; label: string; description: string }> = [
  { key: "SOLVER", label: "Solver", description: "主解题与结构化输出" },
  { key: "TAGGER", label: "Tagger", description: "标签/知识点归类" },
  { key: "OCR", label: "OCR", description: "图片 OCR 与结构化题面提取" },
];

const LOCKED_ENABLED = new Set(["OCR", "SOLVER", "TAGGER"]);

export default function SettingsPage() {
  const { preference, resolvedTheme, setPreference } = useTheme();
  const didInitialLoadRef = useRef(false);
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
  const {
    enabled: agentEnabled,
    isLoading: isLoadingEnabled,
    savingAgent: savingEnabledAgent,
    statusMessage: enabledStatusMessage,
    errorMessage: enabledErrorMessage,
    refresh: refreshAgentEnabled,
    update: updateAgentEnabled,
  } = useAgentEnabledSettings({ lockedKeys: LOCKED_ENABLED });
  const {
    thinking: agentThinking,
    isLoading: isLoadingThinking,
    savingAgent: savingThinkingAgent,
    statusMessage: thinkingStatusMessage,
    errorMessage: thinkingErrorMessage,
    refresh: refreshAgentThinking,
    update: updateAgentThinking,
  } = useAgentThinkingSettings();
  const {
    items: models,
    isLoading: isLoadingModels,
    errorMessage: modelsErrorMessage,
    refresh: refreshModels,
  } = useModelList();

  const sortedModels = useMemo(() => {
    return [...models].filter((m) => m?.id).sort((a, b) => a.id.localeCompare(b.id));
  }, [models]);

  useEffect(() => {
    // Guard against Next.js dev StrictMode double-invocation / accidental remount loops.
    if (didInitialLoadRef.current) return;
    didInitialLoadRef.current = true;

    void refreshAgentModels();
    void refreshModels(false);
    void refreshAgentEnabled();
    void refreshAgentThinking();
  }, [refreshAgentModels, refreshModels, refreshAgentEnabled, refreshAgentThinking]);

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
      {/* Appearance */}
      <SettingsAppearanceSection
        preference={preference}
        resolvedTheme={resolvedTheme}
        onChangePreference={setPreference}
      />

      {/* Model Settings */}
      <SettingsModelSection
        agents={AGENTS}
        sortedModels={sortedModels}
        draft={draft}
        agentModels={agentModels}
        lockedEnabled={LOCKED_ENABLED}
        agentEnabled={agentEnabled}
        agentThinking={agentThinking}
        isDirty={isDirty}
        isSaving={isSaving}
        isLoadingSettings={isLoadingSettings}
        isLoadingModels={isLoadingModels}
        isLoadingEnabled={isLoadingEnabled}
        isLoadingThinking={isLoadingThinking}
        savingEnabledAgent={savingEnabledAgent}
        savingThinkingAgent={savingThinkingAgent}
        statusMessage={statusMessage}
        agentModelsErrorMessage={agentModelsErrorMessage}
        modelsErrorMessage={modelsErrorMessage}
        enabledStatusMessage={enabledStatusMessage}
        enabledErrorMessage={enabledErrorMessage}
        thinkingStatusMessage={thinkingStatusMessage}
        thinkingErrorMessage={thinkingErrorMessage}
        onRefreshModels={refreshModels}
        onReset={handleReset}
        onSave={handleSave}
        onChangeModel={handleChange}
        onToggleEnabled={handleEnabledChange}
        onToggleThinking={handleThinkingChange}
      />
    </Box>
  );
}
