import { Plus, Search } from "lucide-react";
import { IconButton, TextInput, ToggleSwitch, Tooltip } from "@/components/ui/primitives";
import type { ProviderChannel } from "@/features/settings/types";
import { ProviderMark } from "./ProviderMark";
import styles from "./aiSettings.module.css";

export function ChannelRail({
  channels,
  busy,
  query,
  selectedId,
  onCreate,
  onQueryChange,
  onSelect,
  onToggle,
}: {
  channels: ProviderChannel[];
  busy: boolean;
  query: string;
  selectedId: string | null;
  onCreate: () => void;
  onQueryChange: (value: string) => void;
  onSelect: (channel: ProviderChannel) => void;
  onToggle: (channel: ProviderChannel, enabled: boolean) => void;
}) {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleChannels = channels.filter((channel) => (
    !normalizedQuery
    || channel.display_name.toLocaleLowerCase().includes(normalizedQuery)
    || channel.id.toLocaleLowerCase().includes(normalizedQuery)
    || channel.provider.toLocaleLowerCase().includes(normalizedQuery)
  ));

  return (
    <aside className={styles.channelRail} aria-label="AI 渠道列表">
      <div className={styles.railHeader}>
        <h1 className={styles.railTitle}>AI 渠道</h1>
        <Tooltip text="新建渠道">
          <IconButton variant="default" icon={Plus} aria-label="新建渠道" onClick={onCreate} />
        </Tooltip>
      </div>
      <div className={styles.railSearch}>
        <TextInput
          block
          aria-label="搜索渠道"
          placeholder="搜索渠道"
          leadingVisual={Search}
          value={query}
          onChange={(event) => onQueryChange(event.currentTarget.value)}
        />
      </div>
      <div className={styles.railList}>
        {visibleChannels.map((channel) => {
          const selected = selectedId === channel.id;
          const configured = channel.has_secret;
          const switchClass = !configured
            ? styles.channelSwitchIncomplete
            : channel.enabled
              ? styles.channelSwitchEnabled
              : styles.channelSwitchDisabled;
          const statusText = !configured ? "配置未完成：缺少 API Key" : channel.enabled ? "已启用" : "已停用";
          return (
            <div
              key={channel.id}
              className={`${styles.channelItem}${selected ? ` ${styles.channelItemActive}` : ""}`}
            >
              <button
                type="button"
                className={styles.channelSelect}
                aria-current={selected ? "true" : undefined}
                onClick={() => onSelect(channel)}
              >
                <ProviderMark provider={channel.provider} icon={channel.icon} size={34} />
                <span style={{ minWidth: 0 }}>
                  <span className={styles.channelItemName}>{channel.display_name}</span>
                  <span className={styles.channelItemMeta}>{channel.models.length} 个模型 · {channel.id}</span>
                </span>
              </button>
              <span className={styles.channelSwitchWrap}>
                <Tooltip text={statusText}>
                  <span>
                    <ToggleSwitch
                      className={`${styles.channelSwitch} ${switchClass}`}
                      aria-label={`${channel.display_name}：${statusText}`}
                      checked={configured && channel.enabled}
                      disabled={busy || !configured}
                      color="green"
                      onChange={(event) => onToggle(channel, event.currentTarget.checked)}
                    />
                  </span>
                </Tooltip>
              </span>
            </div>
          );
        })}
        {!visibleChannels.length && (
          <div className={styles.emptyState} style={{ minHeight: 140, padding: 18 }}>
            <strong>{channels.length ? "没有匹配的渠道" : "还没有渠道"}</strong>
            <p>{channels.length ? "换个名称或渠道 ID 试试。" : "新建渠道后即可配置密钥和模型。"}</p>
          </div>
        )}
      </div>
    </aside>
  );
}
