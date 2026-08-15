"use client";

import { Box, FormControl, Select, Text, TextInput, ToggleSwitch } from "@/components/ui/primitives";
import sxStyles from "./AgentSettingsRow.sx.module.css";

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
      className={["oops-list-item", sxStyles.sx1].filter(Boolean).join(" ")}

    >
      <Box>
        <Text className={sxStyles.sx2}>[{agent.label}]</Text>
        <Text className={sxStyles.sx3}>{agent.description}</Text>
      </Box>

      <Box className={sxStyles.sx4}>
        <FormControl>
          <FormControl.Label visuallyHidden>Model</FormControl.Label>
          <Select
            value={currentValue}
            onValueChange={(value) => onChangeModel(agent.key, value)}
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
            <Box className={sxStyles.sx5}>
              <Text className={sxStyles.sx6}>Temperature</Text>
              <TextInput
                type="number"
                value={temperature}
                onChange={(e) => onChangeTemperature(agent.key, e.target.value)}
                placeholder="Default"
                className={sxStyles.sx7}
                min={0}
                max={2}
                step={0.1}
              />
            </Box>
          </FormControl>
        )}
      </Box>

      <Box className={sxStyles.sx8}>
        <Box className={sxStyles.sx9}>
          <Text className={sxStyles.agentState} data-status={locked ? "locked" : "enabled"}>
            {locked ? "Required" : "Enabled"}
          </Text>
          <ToggleSwitch
            size="small"
            checked={enabled}
            disabled={locked || isSaving}
            className={sxStyles.sx10}
            onClick={(event) => {
              event.preventDefault();
              if (locked) return;
              onToggleEnabled(agent.key, !enabled);
            }}
            aria-label={`${agent.label} enabled`}
          />
        </Box>

        <Box className={sxStyles.sx11}>
          <Text className={sxStyles.sx12}>Thinking</Text>
          <ToggleSwitch
            size="small"
            checked={thinkingEnabled}
            disabled={isSaving}
            className={sxStyles.sx13}
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
