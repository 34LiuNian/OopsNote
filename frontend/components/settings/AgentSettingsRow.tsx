"use client";

import { Box, FormControl, Select, Spinner, Text, ToggleSwitch } from "@primer/react";

type AgentDescriptor = {
  key: string;
  label: string;
  description: string;
};

type ModelItem = {
  id: string;
};

type AgentSettingsRowProps = {
  agent: AgentDescriptor;
  currentValue: string;
  hasCurrentInList: boolean;
  sortedModels: ModelItem[];
  isLoadingSettings: boolean;
  isSaving: boolean;
  isLoadingModels: boolean;
  locked: boolean;
  enabled: boolean;
  thinkingEnabled: boolean;
  isThisSaving: boolean;
  isThisThinkingSaving: boolean;
  isEnabledBusy: boolean;
  isThinkingBusy: boolean;
  onChangeModel: (agentKey: string, value: string) => void;
  onToggleEnabled: (agentKey: string, nextValue: boolean) => void;
  onToggleThinking: (agentKey: string, nextValue: boolean) => void;
};

export function AgentSettingsRow({
  agent,
  currentValue,
  hasCurrentInList,
  sortedModels,
  isLoadingSettings,
  isSaving,
  isLoadingModels,
  locked,
  enabled,
  thinkingEnabled,
  isThisSaving,
  isThisThinkingSaving,
  isEnabledBusy,
  isThinkingBusy,
  onChangeModel,
  onToggleEnabled,
  onToggleThinking,
}: AgentSettingsRowProps) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: ["1fr", "1fr 1fr auto"],
        gap: 3,
        alignItems: "start",
        p: 2,
        borderBottom: "1px solid",
        borderColor: "border.muted",
      }}
    >
      <Box>
        <Text sx={{ fontWeight: "bold", display: "block" }}>[{agent.label}] 模型</Text>
        <Text sx={{ fontSize: 1, color: "fg.muted" }}>{agent.description}</Text>
      </Box>

      <FormControl>
        <FormControl.Label visuallyHidden>模型</FormControl.Label>
        <Select
          value={currentValue}
          onChange={(e) => onChangeModel(agent.key, e.target.value)}
          disabled={isLoadingSettings || isSaving || isLoadingModels}
          block
        >
          <Select.Option value="">默认（不覆盖）</Select.Option>
          {!hasCurrentInList && <Select.Option value={currentValue}>{currentValue}（当前）</Select.Option>}
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

      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, pt: [0, 1] }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Text sx={{ fontSize: 1, color: locked ? "fg.muted" : "fg.default" }}>
            {locked ? "必开" : "启用"}
          </Text>
          <ToggleSwitch
            size="small"
            checked={enabled}
            disabled={locked || isEnabledBusy}
            sx={{
              "& > span[aria-hidden=\"true\"]": { display: "none" },
              "& button svg": { display: "none" },
            }}
            onClick={(event) => {
              event.preventDefault();
              if (locked) return;
              onToggleEnabled(agent.key, !enabled);
            }}
            aria-label={`${agent.label} 启用`}
          />
          {isThisSaving && <Spinner size="small" />}
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Text sx={{ fontSize: 1, color: "fg.default" }}>思考</Text>
          <ToggleSwitch
            size="small"
            checked={thinkingEnabled}
            disabled={isThinkingBusy}
            sx={{
              "& > span[aria-hidden=\"true\"]": { display: "none" },
              "& button svg": { display: "none" },
            }}
            onClick={(event) => {
              event.preventDefault();
              onToggleThinking(agent.key, !thinkingEnabled);
            }}
            aria-label={`${agent.label} 思考`}
          />
          {isThisThinkingSaving && <Spinner size="small" />}
        </Box>
      </Box>
    </Box>
  );
}
