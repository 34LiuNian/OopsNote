"use client";

import { Box, Button, Heading, Spinner, Text } from "@primer/react";
import { CpuIcon, SyncIcon } from "@primer/octicons-react";
import { AgentSettingsRow } from "./AgentSettingsRow";
import { ErrorBanner } from "../ui/ErrorBanner";
import { sileo } from "sileo";
import { useEffect } from "react";

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
  agentTemperature: Record<string, number>;
  isDirty: boolean;
  isSaving: boolean;
  isLoadingSettings: boolean;
  isLoadingModels: boolean;
  isLoadingEnabled: boolean;
  isLoadingThinking: boolean;
  savingEnabledAgent: string | null;
  savingThinkingAgent: string | null;
  savingTemperatureAgent: string | null;
  statusMessage: string;
  agentModelsErrorMessage: string;
  modelsErrorMessage: string;
  enabledStatusMessage: string;
  enabledErrorMessage: string;
  thinkingStatusMessage: string;
  thinkingErrorMessage: string;
  temperatureErrorMessage: string;
  onRefreshModels: (refreshFromServer: boolean) => void;
  onReset: () => void;
  onSave: () => void;
  onChangeModel: (agentKey: string, value: string) => void;
  onToggleEnabled: (agentKey: string, nextValue: boolean) => void;
  onToggleThinking: (agentKey: string, nextValue: boolean) => void;
  onChangeTemperature: (agentKey: string, value: number | null) => void;
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
  isLoadingEnabled,
  isLoadingThinking,
  savingEnabledAgent,
  savingThinkingAgent,
  savingTemperatureAgent,
  statusMessage,
  agentModelsErrorMessage,
  modelsErrorMessage,
  enabledStatusMessage,
  enabledErrorMessage,
  thinkingStatusMessage,
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
  // 显示 Sileo 通知
  useEffect(() => {
    if (statusMessage) {
      sileo.success({ title: statusMessage });
    }
  }, [statusMessage]);

  useEffect(() => {
    if (enabledStatusMessage) {
      sileo.success({ title: enabledStatusMessage });
    }
  }, [enabledStatusMessage]);

  useEffect(() => {
    if (thinkingStatusMessage) {
      sileo.success({ title: thinkingStatusMessage });
    }
  }, [thinkingStatusMessage]);

  return (
    <Box className="oops-card" sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 3 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <CpuIcon size={16} />
          <Box>
            <Text className="oops-section-subtitle">Models</Text>
            <Heading as="h3" className="oops-section-title" sx={{ m: 0, fontSize: 2 }}>
              模型设置
            </Heading>
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 2 }}>
          <Button onClick={() => onRefreshModels(true)} disabled={isLoadingModels || isSaving} leadingVisual={SyncIcon}>
            {isLoadingModels ? "刷新中..." : "刷新模型列表"}
          </Button>
          <Button onClick={onReset} disabled={!isDirty || isSaving || isLoadingSettings}>
            重置
          </Button>
          <Button variant="primary" onClick={onSave} disabled={!isDirty || isSaving || isLoadingSettings}>
            {isSaving ? "保存中..." : "保存"}
          </Button>
        </Box>
      </Box>

      {isDirty && !isSaving && !isLoadingSettings && (
        <Box className="oops-badge oops-badge-warning" sx={{ mb: 3 }}>
          有未保存更改
        </Box>
      )}
      <ErrorBanner message={agentModelsErrorMessage} />
      <ErrorBanner message={modelsErrorMessage} />
      <ErrorBanner message={enabledErrorMessage} />
      <ErrorBanner message={thinkingErrorMessage} />
      <ErrorBanner message={temperatureErrorMessage} />

      <Box sx={{ p: 3, bg: "canvas.subtle", borderRadius: "var(--oops-radius-sm)", mb: 4 }}>
        <Text as="p" sx={{ fontSize: 1, color: "fg.muted" }}>
          为每个 Agent 选择模型覆盖，或留空使用全局默认值。温度可单独设置，留空则使用全局默认温度。
        </Text>
      </Box>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {agents.map((agent) => {
          const currentValue = draft[agent.key] ?? "";
          const hasCurrentInList = currentValue
            ? sortedModels.some((m) => m.id === currentValue)
            : true;

          const locked = lockedEnabled.has(agent.key);
          const enabled = locked ? true : Boolean(agentEnabled[agent.key] ?? true);
          const isThisSaving = savingEnabledAgent === agent.key;
          const thinkingEnabled = Boolean(agentThinking[agent.key] ?? true);
          const isThisThinkingSaving = savingThinkingAgent === agent.key;
          const isEnabledBusy = isLoadingEnabled || isThisSaving;
          const isThinkingBusy = isLoadingThinking || isThisThinkingSaving;
          const tempValue = agentTemperature[agent.key];
          const isThisTemperatureSaving = savingTemperatureAgent === agent.key;

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
              enabled={enabled}
              thinkingEnabled={thinkingEnabled}
              isThisSaving={isThisSaving}
              isThisThinkingSaving={isThisThinkingSaving}
              isEnabledBusy={isEnabledBusy}
              isThinkingBusy={isThinkingBusy}
              temperature={tempValue}
              isTemperatureSaving={isThisTemperatureSaving}
              onChangeModel={onChangeModel}
              onToggleEnabled={onToggleEnabled}
              onToggleThinking={onToggleThinking}
              onChangeTemperature={onChangeTemperature}
            />
          );
        })}
      </Box>

      <Text as="p" sx={{ fontSize: 1, color: "fg.muted", mt: 3 }}>
        当前已保存覆盖：
        {Object.keys(agentModels).length === 0
          ? "无（全部使用默认模型）"
          : agents
              .map((a) => {
                const v = agentModels[a.key];
                return v ? `${a.key}=${v}` : null;
              })
              .filter(Boolean)
              .join(" · ")}
      </Text>

      <Box sx={{ mt: 3, display: "flex", alignItems: "center", gap: 2 }}>
        {(isLoadingEnabled || Boolean(savingEnabledAgent) || isLoadingThinking || Boolean(savingThinkingAgent)) && (
          <Spinner size="small" />
        )}
        <Text sx={{ fontSize: 1, color: "fg.muted" }}>
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
  );
}
