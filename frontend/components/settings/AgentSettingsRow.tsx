"use client";

import { Box, FormControl, Select, Text, TextInput, ToggleSwitch } from "@primer/react";

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
  temperature: string;
  onChangeModel: (agentKey: string, value: string) => void;
  onToggleEnabled: (agentKey: string, nextValue: boolean) => void;
  onToggleThinking: (agentKey: string, nextValue: boolean) => void;
  onChangeTemperature?: (agentKey: string, value: string) => void;
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
  temperature,
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
          <FormControl.Label visuallyHidden>Model</FormControl.Label>
          <Select
            value={currentValue}
            onChange={(e) => onChangeModel(agent.key, e.target.value)}
            disabled={isLoadingSettings || isSaving || isLoadingModels}
            block
          >
            <Select.Option value="">Default (no override)</Select.Option>
            {!hasCurrentInList && <Select.Option value={currentValue}>{currentValue} (current)</Select.Option>}
            {sortedModels.length === 0 && (
              <Select.Option value="" disabled>
                {isLoadingModels ? "Loading model list..." : "Model list is empty (configure gateway first)"}
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
            <FormControl.Label visuallyHidden>Temperature</FormControl.Label>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Text sx={{ fontSize: 1, color: "fg.muted", whiteSpace: "nowrap" }}>Temperature</Text>
              <TextInput
                type="number"
                value={temperature}
                onChange={(e) => onChangeTemperature(agent.key, e.target.value)}
                placeholder="Default"
                sx={{ width: "80px" }}
                min={0}
                max={2}
                step={0.1}
              />
            </Box>
          </FormControl>
        )}
      </Box>

      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, pt: [0, 1] }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Text sx={{ fontSize: 0, color: locked ? "fg.muted" : "fg.default", whiteSpace: "nowrap" }}>
            {locked ? "Required" : "Enabled"}
          </Text>
          <ToggleSwitch
            size="small"
            checked={enabled}
            disabled={locked || isSaving}
            sx={{
              "& > span[aria-hidden=\"true\"]": { display: "none" },
              "& button svg": { display: "none" },
            }}
            onClick={(event) => {
              event.preventDefault();
              if (locked) return;
              onToggleEnabled(agent.key, !enabled);
            }}
            aria-label={`${agent.label} enabled`}
          />
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Text sx={{ fontSize: 0, color: "fg.default", whiteSpace: "nowrap" }}>Thinking</Text>
          <ToggleSwitch
            size="small"
            checked={thinkingEnabled}
            disabled={isSaving}
            sx={{
              "& > span[aria-hidden=\"true\"]": { display: "none" },
              "& button svg": { display: "none" },
            }}
            onClick={(event) => {
              event.preventDefault();
              onToggleThinking(agent.key, !thinkingEnabled);
            }}
            aria-label={`${agent.label} thinking`}
          />
        </Box>
      </Box>
    </Box>
  );
}
