"use client";

import { Box, Button, Heading, Text } from "@/components/ui/primitives";
import { CpuIcon, SyncIcon } from "@/components/ui/icons";
import { AgentSettingsRow } from "./AgentSettingsRow";
import { ErrorBanner } from "../ui/ErrorBanner";
import { notify } from "@/lib/notify";
import { useEffect } from "react";
import sxStyles from "./SettingsModelSection.sx.module.css";

type AgentDescriptor = {
  key: string;
  label: string;
  description: string;
};

type ModelItem = {
  id: string;
};

type SettingsModelSectionProps = {
  agents: AgentDescriptor[];
  sortedModels: ModelItem[];
  draft: Record<string, string>;
  agentModels: Record<string, string>;
  lockedEnabled: Set<string>;
  agentEnabled: Record<string, boolean>;
  agentThinking: Record<string, boolean>;
  agentTemperature: Record<string, string>;
  isDirty: boolean;
  isSaving: boolean;
  isLoadingSettings: boolean;
  isLoadingModels: boolean;
  statusMessage: string;
  agentModelsErrorMessage: string;
  modelsErrorMessage: string;
  enabledErrorMessage: string;
  thinkingErrorMessage: string;
  temperatureErrorMessage: string;
  onRefreshModels: (refreshFromServer: boolean) => void;
  onReset: () => void;
  onSave: () => void;
  onChangeModel: (agentKey: string, value: string) => void;
  onToggleEnabled: (agentKey: string, nextValue: boolean) => void;
  onToggleThinking: (agentKey: string, nextValue: boolean) => void;
  onChangeTemperature: (agentKey: string, value: string) => void;
};

export function SettingsModelSection({
  agents,
  sortedModels,
  draft,
  agentModels,
  lockedEnabled,
  agentEnabled,
  agentThinking,
  agentTemperature,
  isDirty,
  isSaving,
  isLoadingSettings,
  isLoadingModels,
  statusMessage,
  agentModelsErrorMessage,
  modelsErrorMessage,
  enabledErrorMessage,
  thinkingErrorMessage,
  temperatureErrorMessage,
  onRefreshModels,
  onReset,
  onSave,
  onChangeModel,
  onToggleEnabled,
  onToggleThinking,
  onChangeTemperature,
}: SettingsModelSectionProps) {
  useEffect(() => {
    if (statusMessage) {
      notify.success({ title: statusMessage });
    }
  }, [statusMessage]);

  return (
    <Box className={["oops-card", sxStyles.sx1].filter(Boolean).join(" ")} >
      <Box className={sxStyles.sx2}>
        <Box className={sxStyles.sx3}>
          <CpuIcon size={16} />
          <Box>
            <Text className="oops-section-subtitle">模型</Text>
            <Heading as="h3" className={["oops-section-title", sxStyles.sx4].filter(Boolean).join(" ")} >
              Model and Agent Settings
            </Heading>
          </Box>
        </Box>
        <Box className={sxStyles.sx5}>
          <Button onClick={() => onRefreshModels(true)} disabled={isLoadingModels || isSaving} leadingVisual={SyncIcon}>
            {isLoadingModels ? "正在刷新..." : "刷新模型列表"}
          </Button>
          <Button onClick={onReset} disabled={!isDirty || isSaving || isLoadingSettings}>
            重置
          </Button>
          <Button variant="primary" onClick={onSave} disabled={!isDirty || isSaving || isLoadingSettings}>
            {isSaving ? "正在保存..." : "保存"}
          </Button>
        </Box>
      </Box>

      {isDirty && !isSaving && !isLoadingSettings && (
        <Box className={["oops-badge oops-badge-warning", sxStyles.sx6].filter(Boolean).join(" ")} >
          有未保存更改
        </Box>
      )}
      <ErrorBanner message={agentModelsErrorMessage} />
      <ErrorBanner message={modelsErrorMessage} />
      <ErrorBanner message={enabledErrorMessage} />
      <ErrorBanner message={thinkingErrorMessage} />
      <ErrorBanner message={temperatureErrorMessage} />

      <Box className={sxStyles.sx7}>
        <Text as="p" className={sxStyles.sx8}>
          Edit model override, enabled state, thinking mode, and temperature here, then save them together.
        </Text>
      </Box>

      <Box className={sxStyles.sx9}>
        {agents.map((agent) => {
          const currentValue = draft[agent.key] ?? "";
          const hasCurrentInList = currentValue ? sortedModels.some((m) => m.id === currentValue) : true;
          const locked = lockedEnabled.has(agent.key);

          return (
            <AgentSettingsRow
              key={agent.key}
              agent={agent}
              currentValue={currentValue}
              hasCurrentInList={hasCurrentInList}
              sortedModels={sortedModels}
              isLoadingSettings={isLoadingSettings}
              isSaving={isSaving}
              isLoadingModels={isLoadingModels}
              locked={locked}
              enabled={locked ? true : Boolean(agentEnabled[agent.key] ?? true)}
              thinkingEnabled={Boolean(agentThinking[agent.key] ?? true)}
              temperature={agentTemperature[agent.key] ?? ""}
              onChangeModel={onChangeModel}
              onToggleEnabled={onToggleEnabled}
              onToggleThinking={onToggleThinking}
              onChangeTemperature={onChangeTemperature}
            />
          );
        })}
      </Box>

      <Text as="p" className={sxStyles.sx10}>
        Saved model overrides:
        {Object.keys(agentModels).length === 0
          ? " none (all agents use the default model)"
          : ` ${agents
              .map((a) => {
                const value = agentModels[a.key];
                return value ? `${a.key}=${value}` : null;
              })
              .filter(Boolean)
              .join(" · ")}`}
      </Text>
    </Box>
  );
}
