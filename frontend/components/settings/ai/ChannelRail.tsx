import { Plus, Search } from "lucide-react";
import { IconButton, TextInput, Tooltip } from "@/components/ui/primitives";
import type { ProviderChannel } from "@/features/settings/types";
import { ProviderMark } from "./ProviderMark";
import styles from "./aiSettings.module.css";

export function ChannelRail({
  channels,
  query,
  selectedId,
  onCreate,
  onQueryChange,
  onSelect,
}: {
  channels: ProviderChannel[];
  query: string;
  selectedId: string | null;
  onCreate: () => void;
  onQueryChange: (value: string) => void;
  onSelect: (channel: ProviderChannel) => void;
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
          const statusClass = !channel.enabled
            ? styles.statusDisabled
            : channel.has_secret
              ? styles.statusConnected
              : styles.statusMissing;
          return (
            <button
              key={channel.id}
              type="button"
              className={`${styles.channelItem}${selected ? ` ${styles.channelItemActive}` : ""}`}
              aria-current={selected ? "true" : undefined}
              onClick={() => onSelect(channel)}
            >
              <ProviderMark provider={channel.provider} size={34} />
              <span style={{ minWidth: 0 }}>
                <span className={styles.channelItemName}>{channel.display_name}</span>
                <span className={styles.channelItemMeta}>{channel.models.length} 个模型 · {channel.id}</span>
              </span>
              <span className={`${styles.statusDot} ${statusClass}`} aria-hidden="true" />
            </button>
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
