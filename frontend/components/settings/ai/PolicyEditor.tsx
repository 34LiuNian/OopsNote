import { useMemo, useState } from "react";
import { Check, Eye, Search } from "lucide-react";
import { Button, Drawer, TextInput } from "@/components/ui/primitives";
import {
  findPolicyModel,
  policyModelUnavailableReason,
  type PolicyStage,
} from "@/features/settings/modelOptions";
import type { ProviderChannel, StageSelection } from "@/features/settings/types";
import { ProviderMark } from "./ProviderMark";
import styles from "./aiSettings.module.css";

export type PolicyStageDefinition = {
  id: PolicyStage;
  label: string;
  hint: string;
  capabilityLabel: string;
  icon: typeof Eye;
};

export function PolicyStageCard({
  channels,
  definition,
  onClick,
  selection,
}: {
  channels: ProviderChannel[];
  definition: PolicyStageDefinition;
  onClick: () => void;
  selection: StageSelection;
}) {
  const selected = findPolicyModel(channels, selection);
  const unavailableReason = selected
    ? policyModelUnavailableReason(selected.channel, selected.model, definition.id)
    : selection.channel_id || selection.model_id
      ? "已选择的模型不可用"
      : "尚未选择模型";
  const Icon = definition.icon;

  return (
    <div className={styles.stageWrap}>
      <Button
        variant="default"
        type="button"
        className={`${styles.stageCard}${unavailableReason ? ` ${styles.stageCardInvalid}` : ""}`}
        onClick={onClick}
      >
        <span className={styles.stageHeader}>
          <span>
            <span className={styles.stageTitleLine}><Icon size={17} />{definition.label}</span>
            <span className={styles.stageHint}>{definition.hint}</span>
          </span>
          <span className={styles.stageCapability}>{definition.capabilityLabel}</span>
        </span>

        <span className={styles.stageSelection}>
          {selected ? <ProviderMark provider={selected.channel.provider} icon={selected.channel.icon} size={42} /> : <span className={styles.stageSelectionPlaceholder} aria-hidden="true"><Icon size={20} /></span>}
          <span className={styles.stageSelectionText}>
            <span className={styles.stageChannel}>{selected ? selected.channel.display_name : "等待配置"}</span>
            <span className={styles.stageModel}>{selected ? selected.model.id : "选择阶段模型"}</span>
          </span>
        </span>

        <span className={styles.stageAction}>
          <span className={unavailableReason ? styles.stageStatusInvalid : undefined}>
            {unavailableReason ?? "模型可用"}
          </span>
          <span>{selected ? "更换模型" : "选择模型"}</span>
        </span>
      </Button>
    </div>
  );
}

export function ModelPickerDrawer({
  channels,
  definition,
  opened,
  selection,
  onClose,
  onSelect,
}: {
  channels: ProviderChannel[];
  definition: PolicyStageDefinition | null;
  opened: boolean;
  selection: StageSelection;
  onClose: () => void;
  onSelect: (selection: StageSelection) => void;
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleChannels = useMemo(() => channels.map((channel) => ({
    channel,
    models: channel.models.filter((model) => (
      definition
      && !policyModelUnavailableReason(channel, model, definition.id)
      && (!normalizedQuery || `${model.id} ${model.source} ${channel.display_name}`.toLocaleLowerCase().includes(normalizedQuery))
    )),
  })).filter((group) => group.models.length), [channels, definition, normalizedQuery]);

  return (
    <Drawer
      opened={opened}
      onClose={() => { setQuery(""); onClose(); }}
      position="right"
      size={520}
      title={definition ? `选择 ${definition.label} 模型` : "选择模型"}
      classNames={{ header: styles.drawerHeader, body: styles.drawerBody }}
    >
      <div className={styles.pickerSearch}>
        <TextInput
          block
          autoFocus
          aria-label="搜索可用模型"
          placeholder="搜索渠道或模型"
          leadingVisual={Search}
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
        />
      </div>
      {definition && visibleChannels.map(({ channel, models }) => (
        <section className={styles.pickerGroup} key={channel.id}>
          <div className={styles.pickerGroupTitle}>
            <ProviderMark provider={channel.provider} icon={channel.icon} size={24} />
            {channel.display_name} · {models.length}
          </div>
          {models.map((model) => {
            const selected = selection.channel_id === channel.id && selection.model_id === model.id;
            return (
              <Button
                variant="default"
                key={model.id}
                type="button"
                className={`${styles.pickerOption}${selected ? ` ${styles.pickerOptionSelected}` : ""}`}
                onClick={() => onSelect({ channel_id: channel.id, model_id: model.id })}
                trailingVisual={selected ? Check : undefined}
              >
                <span className={styles.stageSelectionText}>
                  <span className={styles.modelName}>{model.id}</span>
                  <span className={styles.pickerReason}>{model.source} · {definition.capabilityLabel}</span>
                </span>
              </Button>
            );
          })}
        </section>
      ))}
      {definition && !visibleChannels.length && (
        <div className={styles.emptyState}>
          <strong>没有匹配的模型</strong>
          <p>调整搜索词，或先在 AI 渠道中同步并启用模型能力。</p>
        </div>
      )}
    </Drawer>
  );
}
