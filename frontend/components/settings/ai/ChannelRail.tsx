import { useState } from "react";
import { GripVertical, Plus, Search } from "lucide-react";
import { IconButton, TextInput, ToggleSwitch, Tooltip } from "@/components/ui/primitives";
import type { ProviderChannel } from "@/features/settings/types";
import { ProviderMark } from "./ProviderMark";
import styles from "./aiSettings.module.css";

export function ChannelRail({
  channels,
  busy,
  reorderBusy,
  query,
  selectedId,
  onCreate,
  onQueryChange,
  onReorder,
  onSelect,
  onToggle,
}: {
  channels: ProviderChannel[];
  busy: boolean;
  reorderBusy: boolean;
  query: string;
  selectedId: string | null;
  onCreate: () => void;
  onQueryChange: (value: string) => void;
  onReorder: (channelIds: string[]) => void;
  onSelect: (channel: ProviderChannel) => void;
  onToggle: (channel: ProviderChannel, enabled: boolean) => void;
}) {
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<{ id: string; position: "before" | "after" } | null>(null);
  const [dragOrder, setDragOrder] = useState<string[] | null>(null);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const reorderEnabled = !normalizedQuery && channels.length > 1 && !busy && !reorderBusy;
  const visibleChannels = channels.filter((channel) => (
    !normalizedQuery
    || channel.display_name.toLocaleLowerCase().includes(normalizedQuery)
    || channel.id.toLocaleLowerCase().includes(normalizedQuery)
    || channel.provider.toLocaleLowerCase().includes(normalizedQuery)
  ));
  const channelById = new Map(channels.map((channel) => [channel.id, channel]));
  const renderedChannels = dragOrder
    ? dragOrder.map((id) => channelById.get(id)).filter((channel): channel is ProviderChannel => Boolean(channel))
    : visibleChannels;

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
      <div
        className={styles.railList}
        onDragOver={(event) => { if (draggedId) event.preventDefault(); }}
        onDrop={(event) => {
          event.preventDefault();
          if (!draggedId || !dragOrder) return;
          setDraggedId(null);
          setDropTarget(null);
          setDragOrder(null);
          onReorder(dragOrder);
        }}
      >
        {renderedChannels.map((channel) => {
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
              className={`${styles.channelItem}${selected ? ` ${styles.channelItemActive}` : ""}${draggedId === channel.id ? ` ${styles.channelItemDragging}` : ""}${dropTarget?.id === channel.id ? ` ${styles.channelItemDropTarget}` : ""}${dropTarget?.id === channel.id && dropTarget.position === "before" ? ` ${styles.channelItemDropBefore}` : ""}${dropTarget?.id === channel.id && dropTarget.position === "after" ? ` ${styles.channelItemDropAfter}` : ""}`}
              onDragOver={(event) => {
                if (!reorderEnabled || !draggedId || draggedId === channel.id) return;
                event.preventDefault();
                const bounds = event.currentTarget.getBoundingClientRect();
                const position = event.clientY < bounds.top + bounds.height / 2 ? "before" : "after";
                setDropTarget({ id: channel.id, position });
                setDragOrder((current) => {
                  const next = [...(current ?? channels.map((item) => item.id))];
                  const from = next.indexOf(draggedId);
                  if (from < 0) return next;
                  const [moved] = next.splice(from, 1);
                  const insertAt = next.indexOf(channel.id) + (position === "after" ? 1 : 0);
                  next.splice(insertAt, 0, moved);
                  return next;
                });
              }}
              onDragLeave={() => { if (dropTarget?.id === channel.id) setDropTarget(null); }}
            >
              <IconButton
                variant="invisible"
                size="small"
                icon={GripVertical}
                className={`${styles.dragHandle}${!reorderEnabled ? ` ${styles.dragHandleDisabled}` : ""}`}
                aria-label={`拖动 ${channel.display_name} 调整顺序`}
                draggable={reorderEnabled}
                tabIndex={reorderEnabled ? 0 : -1}
                onDragStart={(event) => {
                  setDraggedId(channel.id);
                  setDragOrder(channels.map((item) => item.id));
                  event.dataTransfer.effectAllowed = "move";
                  event.dataTransfer.setData("text/plain", channel.id);
                }}
                onDragEnd={() => { setDraggedId(null); setDropTarget(null); setDragOrder(null); }}
                onKeyDown={(event) => {
                  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
                  event.preventDefault();
                  const current = channels.findIndex((item) => item.id === channel.id);
                  const target = current + (event.key === "ArrowUp" ? -1 : 1);
                  if (current < 0 || target < 0 || target >= channels.length) return;
                  const next = channels.map((item) => item.id);
                  [next[current], next[target]] = [next[target], next[current]];
                  onReorder(next);
                }}
              />
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
