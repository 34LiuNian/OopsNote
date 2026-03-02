"use client";

import { Box, FormControl, Select, Spinner, Text, TextInput, ToggleSwitch } from "@primer/react";

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
  temperature?: number | undefined;
  isTemperatureSaving?: boolean;
  onChangeModel: (agentKey: string, value: string) => void;
  onToggleEnabled: (agentKey: string, nextValue: boolean) => void;
  onToggleThinking: (agentKey: string, nextValue: boolean) => void;
  onChangeTemperature?: (agentKey: string, value: number | null) => void;
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
  temperature,
  isTemperatureSaving,
  onChangeModel,
  onToggleEnabled,
  onToggleThinking,
  onChangeTemperature,
}: AgentSettingsRowProps) {
  return (
    <Box
      className="oops-list-item"
      sx={{
        display: "grid",
        gridTemplateColumns: ["1fr", "180px 1fr auto"],
        gap: 3,
        alignItems: "start",
        px: 3,
        py: 3,
        borderBottom: "1px solid",
        borderColor: "border.muted",
      }}
    >
      <Box>
        <Text sx={{ fontWeight: 600, display: "block", fontSize: 1 }}>[{agent.label}]</Text>
        <Text sx={{ fontSize: 0, color: "fg.muted" }}>{agent.description}</Text>
      </Box>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
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

        {onChangeTemperature && (
          <FormControl>
            <FormControl.Label visuallyHidden>温度</FormControl.Label>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Text sx={{ fontSize: 1, color: "fg.muted", whiteSpace: "nowrap" }}>温度</Text>
              <TextInput
                type="number"
                value={temperature != null ? String(temperature) : ""}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === "") {
                    onChangeTemperature(agent.key, null);
                  } else {
                    const num = parseFloat(val);
                    if (!isNaN(num)) onChangeTemperature(agent.key, num);
                  }
                }}
                placeholder="默认"
                sx={{ width: "80px" }}
                min={0}
                max={2}
                step={0.1}
              />
              {isTemperatureSaving && <Spinner size="small" />}
            </Box>
          </FormControl>
        )}
      </Box>

      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, pt: [0, 1] }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Text sx={{ fontSize: 0, color: locked ? "fg.muted" : "fg.default", whiteSpace: "nowrap" }}>
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
          <Text sx={{ fontSize: 0, color: "fg.default", whiteSpace: "nowrap" }}>思考</Text>
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
