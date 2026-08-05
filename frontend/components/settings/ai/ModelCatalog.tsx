import { Search, RefreshCw, Grid2X2, Power, Eye, Wrench } from "lucide-react";
import { Button, TextInput, ToggleSwitch, Tooltip } from "@/components/ui/primitives";
import type { ChannelModel, ProviderChannel } from "@/features/settings/types";
import { ProviderMark } from "./ProviderMark";
import styles from "./aiSettings.module.css";

type Filter = "all" | "enabled" | "tool" | "vision";

const FILTERS: { id: Filter; label: string; icon: typeof Grid2X2 }[] = [
  { id: "all", label: "全部", icon: Grid2X2 },
  { id: "enabled", label: "已启用", icon: Power },
  { id: "tool", label: "Tool", icon: Wrench },
  { id: "vision", label: "Vision", icon: Eye },
];

export function ModelCatalog({
  busy,
  busyModelId,
  channel,
  filter,
  query,
  onFilterChange,
  onPatch,
  onQueryChange,
  onSync,
}: {
  busy: boolean;
  busyModelId: string | null;
  channel: ProviderChannel;
  filter: Filter;
  query: string;
  onFilterChange: (filter: Filter) => void;
  onPatch: (model: ChannelModel, patch: { enabled?: boolean; capability?: { tool_calling: boolean; vision: boolean } }) => void;
  onQueryChange: (value: string) => void;
  onSync: () => void;
}) {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const sortedModels = [...channel.models].sort((left, right) => (
    Number(right.enabled) - Number(left.enabled) || left.id.localeCompare(right.id)
  ));
  const visibleModels = sortedModels.filter((model) => {
    if (normalizedQuery && !`${model.id} ${model.source}`.toLocaleLowerCase().includes(normalizedQuery)) return false;
    if (filter === "enabled") return model.enabled;
    if (filter === "tool") return model.capability.tool_calling;
    if (filter === "vision") return model.capability.vision;
    return true;
  });
  const counts: Record<Filter, number> = {
    all: channel.models.length,
    enabled: channel.models.filter((model) => model.enabled).length,
    tool: channel.models.filter((model) => model.capability.tool_calling).length,
    vision: channel.models.filter((model) => model.capability.vision).length,
  };

  return (
    <section className={styles.catalog} aria-labelledby="model-catalog-title">
      <div className={styles.catalogHeader}>
        <h2 id="model-catalog-title" className={styles.sectionTitle}>
          模型目录 <span className={styles.sectionMeta}>{channel.models.length} 个模型</span>
        </h2>
        <Button variant="default" leadingVisual={RefreshCw} onClick={onSync} disabled={!channel.has_secret || busy}>
          同步模型
        </Button>
      </div>

      <div className={styles.catalogToolbar}>
        <div className={styles.filterTabs} role="tablist" aria-label="模型筛选">
          {FILTERS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={filter === id}
              className={`${styles.filterTab}${filter === id ? ` ${styles.filterTabActive}` : ""}`}
              onClick={() => onFilterChange(id)}
            >
              <Icon size={14} />{label} ({counts[id]})
            </button>
          ))}
        </div>
        <div className={styles.catalogSearch}>
          <TextInput
            block
            aria-label="搜索模型"
            placeholder="搜索模型"
            leadingVisual={Search}
            value={query}
            onChange={(event) => onQueryChange(event.currentTarget.value)}
          />
        </div>
      </div>

      <div className={styles.modelList}>
        {visibleModels.map((model) => {
          const rowBusy = busyModelId === model.id;
          return (
            <div className={styles.modelRow} key={model.id}>
              <ProviderMark provider={channel.provider} icon={channel.icon} size={36} />
              <div style={{ minWidth: 0 }}>
                <div className={styles.modelNameLine}>
                  <span className={styles.modelName}>{model.id}</span>
                  <span className={styles.modelIdTag}>{model.source}</span>
                </div>
                {!model.capability.tool_calling && !model.capability.vision && <div className={styles.modelMeta}>能力未确认</div>}
              </div>
              <div className={styles.modelActions}>
                <Tooltip text={model.capability.vision ? "关闭 Vision 能力" : "启用 Vision 能力"}>
                  <button
                    type="button"
                    className={`${styles.capabilityButton}${model.capability.vision ? ` ${styles.capabilityActiveVision}` : ""}`}
                    aria-label={`${model.id} Vision`}
                    aria-pressed={model.capability.vision}
                    disabled={rowBusy}
                    onClick={() => onPatch(model, { capability: { ...model.capability, vision: !model.capability.vision } })}
                  ><Eye size={15} /></button>
                </Tooltip>
                <Tooltip text={model.capability.tool_calling ? "关闭 Tool Calling" : "启用 Tool Calling"}>
                  <button
                    type="button"
                    className={`${styles.capabilityButton}${model.capability.tool_calling ? ` ${styles.capabilityActiveTool}` : ""}`}
                    aria-label={`${model.id} Tool Calling`}
                    aria-pressed={model.capability.tool_calling}
                    disabled={rowBusy}
                    onClick={() => onPatch(model, { capability: { ...model.capability, tool_calling: !model.capability.tool_calling } })}
                  ><Wrench size={15} /></button>
                </Tooltip>
                <span className={styles.modelSwitch}>
                  <ToggleSwitch
                    aria-label={`${model.id} 启用`}
                    checked={model.enabled}
                    disabled={rowBusy}
                    onChange={(event) => onPatch(model, { enabled: event.currentTarget.checked })}
                  />
                </span>
              </div>
            </div>
          );
        })}
        {!visibleModels.length && (
          <div className={styles.emptyState}>
            <strong>{channel.models.length ? "没有匹配的模型" : "模型目录为空"}</strong>
            <p>{channel.models.length ? "调整筛选条件或搜索词。" : channel.has_secret ? "同步渠道以获取最新模型。" : "先保存访问凭据，再同步模型目录。"}</p>
          </div>
        )}
      </div>
    </section>
  );
}

export type ModelCatalogFilter = Filter;
