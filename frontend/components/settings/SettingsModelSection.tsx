"use client";

import { Box, Button, Flash, Heading, Label, Spinner, Text } from "@primer/react";
import { SyncIcon } from "@primer/octicons-react";
import { AgentSettingsRow } from "./AgentSettingsRow";

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
  isDirty: boolean;
  isSaving: boolean;
  isLoadingSettings: boolean;
  isLoadingModels: boolean;
  isLoadingEnabled: boolean;
  isLoadingThinking: boolean;
  savingEnabledAgent: string | null;
  savingThinkingAgent: string | null;
  statusMessage: string;
  agentModelsErrorMessage: string;
  modelsErrorMessage: string;
  enabledStatusMessage: string;
  enabledErrorMessage: string;
  thinkingStatusMessage: string;
  thinkingErrorMessage: string;
  onRefreshModels: (refreshFromServer: boolean) => void;
  onReset: () => void;
  onSave: () => void;
  onChangeModel: (agentKey: string, value: string) => void;
  onToggleEnabled: (agentKey: string, nextValue: boolean) => void;
  onToggleThinking: (agentKey: string, nextValue: boolean) => void;
};

export function SettingsModelSection({
  agents,
  sortedModels,
  draft,
  agentModels,
  lockedEnabled,
  agentEnabled,
  agentThinking,
  isDirty,
  isSaving,
  isLoadingSettings,
  isLoadingModels,
  isLoadingEnabled,
  isLoadingThinking,
  savingEnabledAgent,
  savingThinkingAgent,
  statusMessage,
  agentModelsErrorMessage,
  modelsErrorMessage,
  enabledStatusMessage,
  enabledErrorMessage,
  thinkingStatusMessage,
  thinkingErrorMessage,
  onRefreshModels,
  onReset,
  onSave,
  onChangeModel,
  onToggleEnabled,
  onToggleThinking,
}: SettingsModelSectionProps) {
  return (
    <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Text sx={{ fontSize: 0, color: "fg.muted", textTransform: "uppercase" }}>Settings</Text>
          <Heading as="h2" sx={{ fontSize: 3 }}>
            模型设置
          </Heading>
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
        <Label variant="attention" sx={{ mb: 3, display: "inline-block" }}>
          有未保存更改
        </Label>
      )}
      {statusMessage && <Flash variant="success" sx={{ mb: 3 }}>{statusMessage}</Flash>}
      {agentModelsErrorMessage && <Flash variant="danger" sx={{ mb: 3 }}>{agentModelsErrorMessage}</Flash>}
      {modelsErrorMessage && <Flash variant="danger" sx={{ mb: 3 }}>{modelsErrorMessage}</Flash>}
      {enabledStatusMessage && <Flash variant="success" sx={{ mb: 3 }}>{enabledStatusMessage}</Flash>}
      {enabledErrorMessage && <Flash variant="danger" sx={{ mb: 3 }}>{enabledErrorMessage}</Flash>}
      {thinkingStatusMessage && <Flash variant="success" sx={{ mb: 3 }}>{thinkingStatusMessage}</Flash>}
      {thinkingErrorMessage && <Flash variant="danger" sx={{ mb: 3 }}>{thinkingErrorMessage}</Flash>}

      <Box sx={{ p: 3, bg: "canvas.subtle", borderRadius: 2, mb: 4 }}>
        <Text as="p" sx={{ mb: 1 }}>
          说明：模型列表来自后端的 <strong>/models</strong>（会转发到 OpenAI 兼容网关的 <strong>/v1/models</strong>）。
        </Text>
        <Text as="p" sx={{ fontSize: 1, color: "fg.muted" }}>
          如果提示缺少配置，请先在后端设置 <strong>OPENAI_BASE_URL</strong>（例如 http://127.0.0.1:23333/v1）和
          <strong>OPENAI_API_KEY</strong>，或在 agent TOML 配置里填写 default.base_url/default.api_key。
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
          const isControlBusy = isLoadingEnabled || isThisSaving || isLoadingThinking || isThisThinkingSaving;

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
              isControlBusy={isControlBusy}
              onChangeModel={onChangeModel}
              onToggleEnabled={onToggleEnabled}
              onToggleThinking={onToggleThinking}
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
