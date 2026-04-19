"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Button, Checkbox, Flash, Heading, Text } from "@primer/react";
import { GearIcon } from "@primer/octicons-react";
import { useTheme } from "../../components/providers/ThemeProvider";
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
  { key: "SOLVER", label: "Solver", description: "Problem solving and structured output" },
  { key: "TAGGER", label: "Tagger", description: "Tags and knowledge point classification" },
  { key: "OCR", label: "OCR", description: "OCR and structured problem extraction" },
];

const LOCKED_ENABLED = new Set(["OCR", "SOLVER", "TAGGER"]);

export default function SettingsPage() {
  const { preference, resolvedTheme, setPreference } = useTheme();
  const didInitialLoadRef = useRef(false);

  const {
    agentModels,
    draft,
    isLoading: isLoadingSettings,
    isSaving: isSavingModels,
    isDirty: isModelsDirty,
    statusMessage: agentModelsStatusMessage,
    errorMessage: agentModelsErrorMessage,
    refresh: refreshAgentModels,
    setDraftValue,
    reset: resetAgentModels,
    save: saveAgentModels,
  } = useAgentModelsSettings();

  const {
    draft: agentEnabledDraft,
    isLoading: isLoadingEnabled,
    isSaving: isSavingEnabled,
    isDirty: isEnabledDirty,
    statusMessage: enabledStatusMessage,
    errorMessage: enabledErrorMessage,
    refresh: refreshAgentEnabled,
    setDraftValue: setAgentEnabledDraftValue,
    reset: resetAgentEnabled,
    save: saveAgentEnabled,
  } = useAgentEnabledSettings({ lockedKeys: LOCKED_ENABLED });

  const {
    draft: agentThinkingDraft,
    isLoading: isLoadingThinking,
    isSaving: isSavingThinking,
    isDirty: isThinkingDirty,
    statusMessage: thinkingStatusMessage,
    errorMessage: thinkingErrorMessage,
    refresh: refreshAgentThinking,
    setDraftValue: setAgentThinkingDraftValue,
    reset: resetAgentThinking,
    save: saveAgentThinking,
  } = useAgentThinkingSettings();

  const {
    draft: agentTemperatureDraft,
    isLoading: isLoadingTemperature,
    isSaving: isSavingTemperature,
    isDirty: isTemperatureDirty,
    statusMessage: temperatureStatusMessage,
    errorMessage: temperatureErrorMessage,
    refresh: refreshAgentTemperature,
    setDraftValue: setAgentTemperatureDraftValue,
    reset: resetAgentTemperature,
    save: saveAgentTemperature,
  } = useAgentTemperatureSettings();

  const {
    items: models,
    isLoading: isLoadingModels,
    errorMessage: modelsErrorMessage,
    refresh: refreshModels,
  } = useModelList();

  const gateway = useGatewaySettings();
  const debug = useDebugSettings();
  const systemInfo = useSystemInfo();

  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  const [savedRegistrationEnabled, setSavedRegistrationEnabled] = useState(false);
  const [registrationLoaded, setRegistrationLoaded] = useState(false);
  const [registrationSaving, setRegistrationSaving] = useState(false);
  const [registrationError, setRegistrationError] = useState("");
  const [registrationStatus, setRegistrationStatus] = useState("");

  const sortedModels = useMemo(() => {
    return [...models].filter((m) => m?.id).sort((a, b) => a.id.localeCompare(b.id));
  }, [models]);

  const modelSectionStatusMessage =
    temperatureStatusMessage || thinkingStatusMessage || enabledStatusMessage || agentModelsStatusMessage;

  const isModelSectionDirty =
    isModelsDirty || isEnabledDirty || isThinkingDirty || isTemperatureDirty;
  const isModelSectionSaving =
    isSavingModels || isSavingEnabled || isSavingThinking || isSavingTemperature;
  const isModelSectionLoading =
    isLoadingSettings || isLoadingEnabled || isLoadingThinking || isLoadingTemperature;

  const isRegistrationDirty = registrationEnabled !== savedRegistrationEnabled;

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
        const next = Boolean(value.enabled);
        setRegistrationEnabled(next);
        setSavedRegistrationEnabled(next);
      })
      .catch((err) => {
        setRegistrationError(err instanceof Error ? err.message : "Failed to load registration settings");
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

  const handleResetRegistration = useCallback(() => {
    setRegistrationEnabled(savedRegistrationEnabled);
    setRegistrationError("");
    setRegistrationStatus("");
  }, [savedRegistrationEnabled]);

  const handleSaveRegistration = useCallback(async () => {
    setRegistrationError("");
    setRegistrationStatus("");
    setRegistrationSaving(true);
    try {
      const next = await updateRegistrationSettings({ enabled: registrationEnabled });
      const savedValue = Boolean(next.enabled);
      setRegistrationEnabled(savedValue);
      setSavedRegistrationEnabled(savedValue);
      setRegistrationStatus("Registration settings saved");
    } catch (err) {
      setRegistrationError(err instanceof Error ? err.message : "Failed to save registration settings");
    } finally {
      setRegistrationSaving(false);
    }
  }, [registrationEnabled]);

  const handleSaveModelSection = useCallback(async () => {
    if (isModelsDirty) {
      await saveAgentModels();
    }
    if (isEnabledDirty) {
      await saveAgentEnabled();
    }
    if (isThinkingDirty) {
      await saveAgentThinking();
    }
    if (isTemperatureDirty) {
      await saveAgentTemperature();
    }
  }, [
    isModelsDirty,
    isEnabledDirty,
    isThinkingDirty,
    isTemperatureDirty,
    saveAgentModels,
    saveAgentEnabled,
    saveAgentThinking,
    saveAgentTemperature,
  ]);

  const handleResetModelSection = useCallback(() => {
    resetAgentModels();
    resetAgentEnabled();
    resetAgentThinking();
    resetAgentTemperature();
  }, [resetAgentEnabled, resetAgentModels, resetAgentTemperature, resetAgentThinking]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box className="oops-section-header" sx={{ border: "none !important", mb: 0, pb: 2 }}>
        <GearIcon size={20} />
        <Box sx={{ flex: 1 }}>
          <Text className="oops-section-subtitle">Settings</Text>
          <Heading as="h2" className="oops-section-title" sx={{ m: 0 }}>
            Settings
          </Heading>
        </Box>
      </Box>

      <SettingsAppearanceSection
        preference={preference}
        resolvedTheme={resolvedTheme}
        onChangePreference={setPreference}
      />

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

      <SettingsModelSection
        agents={AGENTS}
        sortedModels={sortedModels}
        draft={draft}
        agentModels={agentModels}
        lockedEnabled={LOCKED_ENABLED}
        agentEnabled={agentEnabledDraft}
        agentThinking={agentThinkingDraft}
        agentTemperature={agentTemperatureDraft}
        isDirty={isModelSectionDirty}
        isSaving={isModelSectionSaving}
        isLoadingSettings={isModelSectionLoading}
        isLoadingModels={isLoadingModels}
        statusMessage={modelSectionStatusMessage}
        agentModelsErrorMessage={agentModelsErrorMessage}
        modelsErrorMessage={modelsErrorMessage}
        enabledErrorMessage={enabledErrorMessage}
        thinkingErrorMessage={thinkingErrorMessage}
        temperatureErrorMessage={temperatureErrorMessage}
        onRefreshModels={refreshModels}
        onReset={handleResetModelSection}
        onSave={handleSaveModelSection}
        onChangeModel={setDraftValue}
        onToggleEnabled={setAgentEnabledDraftValue}
        onToggleThinking={setAgentThinkingDraftValue}
        onChangeTemperature={setAgentTemperatureDraftValue}
      />

      <Box className="oops-card" sx={{ p: 3, display: "grid", gap: 3 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 3 }}>
          <Box>
            <Heading as="h3" sx={{ fontSize: 2, mb: 1 }}>
              Registration
            </Heading>
            <Text sx={{ color: "fg.muted", fontSize: 1 }}>
              Control whether self-service registration is available on the login page.
            </Text>
          </Box>
          <Box sx={{ display: "flex", gap: 2 }}>
            <Button onClick={handleResetRegistration} disabled={!isRegistrationDirty || registrationSaving || !registrationLoaded}>
              Reset
            </Button>
            <Button
              variant="primary"
              onClick={() => void handleSaveRegistration()}
              disabled={!isRegistrationDirty || registrationSaving || !registrationLoaded}
            >
              {registrationSaving ? "Saving..." : "Save"}
            </Button>
          </Box>
        </Box>

        {isRegistrationDirty && !registrationSaving && registrationLoaded && (
          <Box className="oops-badge oops-badge-warning">Unsaved changes</Box>
        )}
        {!registrationLoaded ? <Text sx={{ color: "fg.muted" }}>Loading...</Text> : null}
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Checkbox
            checked={registrationEnabled}
            onChange={(event) => setRegistrationEnabled(event.target.checked)}
            disabled={!registrationLoaded || registrationSaving}
          />
          <Text>Allow self-service registration</Text>
        </Box>
        {registrationError ? <Flash variant="danger">{registrationError}</Flash> : null}
        {registrationStatus ? <Flash variant="success">{registrationStatus}</Flash> : null}
      </Box>

      <SettingsDebugSection
        settings={debug.settings}
        draft={debug.draft}
        isLoading={debug.isLoading}
        isSaving={debug.isSaving}
        isDirty={debug.isDirty}
        statusMessage={debug.statusMessage}
        errorMessage={debug.errorMessage}
        onToggle={debug.setDraftValue}
        onReset={debug.reset}
        onSave={debug.save}
      />

      <SettingsSystemInfoSection
        info={systemInfo.info}
        isLoading={systemInfo.isLoading}
        errorMessage={systemInfo.errorMessage}
      />
    </Box>
  );
}
