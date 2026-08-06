"use client";

import { useDeferredValue, useMemo, useState } from "react";
import { PasswordInput } from "@mantine/core";
import { CircleCheck, CircleX, Copy, PlugZap, Save, ShieldAlert, Trash2 } from "lucide-react";
import { useAuth } from "@/components/providers/AuthProvider";
import { Box, Button, FormControl, Heading, IconButton, Select, Spinner, Text, TextInput, Tooltip } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { isAdminUser } from "@/lib/auth";
import { notify } from "@/lib/notify";
import { confirmAction } from "@/lib/confirm";
import { formatApiError } from "@/lib/errorFormatter";
import { getChannelCredential } from "@/features/settings/api";
import { useAiChannels, useAiChannelMutations } from "@/features/settings/useAiProviders";
import type { ChannelDraft, ChannelModel, ProviderChannel, ProviderValidation } from "@/features/settings/types";
import { ChannelRail, ModelCatalog, type ModelCatalogFilter, ProviderIconPicker, ProviderMark, providerLabel } from "@/components/settings/ai";
import styles from "@/components/settings/ai/aiSettings.module.css";

const PROVIDERS = [
  { value: "deepseek", label: "DeepSeek" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google Gemini" },
  { value: "openai-compatible", label: "OpenAI Compatible" },
];

const PROVIDER_DEFAULT_URLS: Record<string, string | null> = {
  deepseek: "https://api.deepseek.com/v1",
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com",
  google: "https://generativelanguage.googleapis.com",
  "openai-compatible": null,
};

const EMPTY_DRAFT: ChannelDraft = {
  id: "",
  display_name: "",
  provider: "deepseek",
  icon: null,
  base_url: PROVIDER_DEFAULT_URLS.deepseek,
  enabled: true,
};

const MASKED_SECRET = "********";

function draftFrom(channel: ProviderChannel): ChannelDraft {
  return {
    id: channel.id,
    display_name: channel.display_name,
    provider: channel.provider,
    icon: channel.icon,
    base_url: channel.base_url,
    enabled: channel.enabled,
  };
}

function formatDate(value: string | null): string {
  if (!value) return "未记录";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

export default function AiChannelsPage() {
  const { user, loading } = useAuth();
  const isAdmin = isAdminUser(user);
  const channels = useAiChannels(!loading && isAdmin);
  const mutations = useAiChannelMutations();
  const items = useMemo(() => channels.data?.items ?? [], [channels.data]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [channelQuery, setChannelQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [iconPickerOpen, setIconPickerOpen] = useState(false);
  const [draft, setDraft] = useState<ChannelDraft>(EMPTY_DRAFT);
  const [secretDraft, setSecretDraft] = useState("");
  const [secretDirty, setSecretDirty] = useState(false);
  const [secretRevealed, setSecretRevealed] = useState(false);
  const [secretVisible, setSecretVisible] = useState(false);
  const [revealingSecret, setRevealingSecret] = useState(false);
  const [credentialError, setCredentialError] = useState("");
  const [modelFilter, setModelFilter] = useState<ModelCatalogFilter>("all");
  const [modelQuery, setModelQuery] = useState("");
  const [busyModelId, setBusyModelId] = useState<string | null>(null);
  const [checkModelId, setCheckModelId] = useState("");
  const [checkResult, setCheckResult] = useState<ProviderValidation | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const selected = items.find((item) => item.id === selectedId) ?? (!creating ? items[0] ?? null : null);
  const deferredSelected = useDeferredValue(selected);
  const connectivityModels = selected?.models.filter((model) => model.enabled) ?? [];
  const effectiveCheckModelId = connectivityModels.some((model) => model.id === checkModelId)
    ? checkModelId
    : connectivityModels[0]?.id ?? "";
  const activeDraft = selected && draft.id === selected.id ? draft : selected ? draftFrom(selected) : draft;
  const busy = Object.entries(mutations)
    .filter(([key]) => key !== "reorder" && key !== "check")
    .some(([, mutation]) => mutation.isPending);
  const infoDirty = creating || Boolean(selected && (
    activeDraft.display_name !== selected.display_name
    || activeDraft.provider !== selected.provider
    || activeDraft.icon !== selected.icon
    || activeDraft.base_url !== selected.base_url
  ));
  const canSave = Boolean(
    (creating || infoDirty || secretDirty)
    && activeDraft.id.trim()
    && activeDraft.display_name.trim()
    && (!secretDirty || secretDraft.trim()),
  );
  const displayedSecret = secretRevealed || secretDirty
    ? secretDraft
    : selected?.has_secret
      ? MASKED_SECRET
      : "";

  if (loading) return <Box sx={{ p: 4 }}><Spinner size="medium" /></Box>;
  if (!isAdmin) return <Box sx={{ p: 4, display: "flex", gap: 2, alignItems: "center" }}><ShieldAlert size={22} /><Box><Heading order={2}>无权访问</Heading><Text sx={{ color: "fg.muted" }}>AI Provider 配置仅管理员可用。</Text></Box></Box>;

  function resetCredentialDraft() {
    setSecretDraft("");
    setSecretDirty(false);
    setSecretRevealed(false);
    setSecretVisible(false);
    setCredentialError("");
  }

  function choose(channel: ProviderChannel) {
    setCreating(false);
    setIconPickerOpen(false);
    setSelectedId(channel.id);
    setDraft(draftFrom(channel));
    resetCredentialDraft();
    setErrorMessage("");
    setModelFilter("all");
    setModelQuery("");
    setCheckModelId(channel.models.find((model) => model.enabled)?.id ?? "");
    setCheckResult(null);
  }

  async function checkConnectivity() {
    if (!selected || !effectiveCheckModelId) return;
    setErrorMessage("");
    setCheckResult(null);
    try {
      const result = await mutations.check.mutateAsync({ channelId: selected.id, modelId: effectiveCheckModelId });
      setCheckResult(result.validation);
    } catch (error) {
      setErrorMessage(formatApiError(error, "连通性检查失败"));
    }
  }

  async function reorderChannelList(channelIds: string[]) {
    try {
      await mutations.reorder.mutateAsync(channelIds);
    } catch (error) {
      setErrorMessage(formatApiError(error, "渠道排序保存失败"));
    }
  }

  function beginCreate() {
    setCreating(true);
    setIconPickerOpen(false);
    setSelectedId(null);
    setDraft({ ...EMPTY_DRAFT });
    resetCredentialDraft();
    setErrorMessage("");
  }

  async function saveAll() {
    setErrorMessage("");
    setCredentialError("");
    let channel = selected;
    let syncedCount: number | null = null;
    const wasCreating = creating;

    try {
      if (creating) {
        const result = await mutations.create.mutateAsync(activeDraft);
        channel = result.channel;
        setCreating(false);
        setSelectedId(result.channel.id);
        setDraft(draftFrom(result.channel));
      } else if (selected && infoDirty) {
        const { id: _id, ...payload } = activeDraft;
        const result = await mutations.update.mutateAsync({ channelId: selected.id, payload });
        channel = result.channel;
        setDraft(draftFrom(result.channel));
      }
    } catch (error) {
      setErrorMessage(formatApiError(error, "渠道信息保存失败"));
      return;
    }

    if (!channel) return;

    try {
      if (secretDirty) {
        const result = await mutations.credential.mutateAsync({ channelId: channel.id, secret: secretDraft.trim() });
        channel = result.channel;
        syncedCount = result.discovery.count;
        resetCredentialDraft();
      } else if (channel.has_secret) {
        const result = await mutations.sync.mutateAsync(channel.id);
        channel = result.channel;
        syncedCount = result.discovery.count;
      }
    } catch (error) {
      setCredentialError(formatApiError(error, secretDirty ? "凭据验证失败" : "模型同步失败"));
      return;
    }

    setCreating(false);
    setSelectedId(channel.id);
    setDraft(draftFrom(channel));
    notify.success({
      title: wasCreating ? "渠道已创建" : "渠道已保存",
      description: syncedCount == null ? "渠道信息已更新。" : `凭据验证通过，已同步 ${syncedCount} 个模型。`,
    });
  }

  async function revealSecret() {
    if (!selected?.has_secret || revealingSecret) return;
    setCredentialError("");
    setRevealingSecret(true);
    try {
      const result = await getChannelCredential(selected.id);
      setSecretDraft(result.secret);
      setSecretRevealed(true);
      setSecretVisible(true);
    } catch (error) {
      setCredentialError(formatApiError(error, "无法读取已保存密钥"));
    } finally {
      setRevealingSecret(false);
    }
  }

  function changeSecret(value: string) {
    if (!secretRevealed && !secretDirty && selected?.has_secret && value === MASKED_SECRET) return;
    setSecretDraft(value === MASKED_SECRET && !secretRevealed ? "" : value);
    setSecretDirty(value !== MASKED_SECRET);
    setCredentialError("");
  }

  function changeSecretVisibility(visible: boolean) {
    if (!visible) {
      setSecretVisible(false);
      return;
    }
    if (secretRevealed || secretDirty || !selected?.has_secret) {
      setSecretVisible(true);
      return;
    }
    void revealSecret();
  }

  async function syncModels() {
    if (!selected) return;
    setErrorMessage("");
    try {
      const result = await mutations.sync.mutateAsync(selected.id);
      notify.success({ title: "模型目录已同步", description: `${result.validation.message}，共 ${result.discovery.count} 个模型。` });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "模型同步失败");
    }
  }

  async function patchModel(model: ChannelModel, patch: { enabled?: boolean; capability?: { tool_calling: boolean; vision: boolean } }) {
    if (!selected) return;
    setBusyModelId(model.id);
    setErrorMessage("");
    try {
      await mutations.model.mutateAsync({ channelId: selected.id, modelId: model.id, payload: patch });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "模型配置失败");
    } finally {
      setBusyModelId(null);
    }
  }

  async function setEnabled(channel: ProviderChannel, enabled: boolean) {
    setErrorMessage("");
    try {
      await mutations.update.mutateAsync({ channelId: channel.id, payload: { enabled } });
      if (selected?.id === channel.id) setDraft((current) => ({ ...current, enabled }));
      notify.success({ title: enabled ? "渠道已启用" : "渠道已停用" });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "渠道状态更新失败");
    }
  }

  function toggleEnabled(channel: ProviderChannel, enabled: boolean) {
    if (enabled) {
      void setEnabled(channel, true);
      return;
    }
    confirmAction({
      title: `停用 ${channel.display_name}`,
      message: "现有 run 不受影响，后续策略不能使用该渠道。",
      confirmLabel: "停用",
      destructive: true,
      onConfirm: () => setEnabled(channel, false),
    });
  }

  async function performDelete() {
    if (!selected) return;
    setErrorMessage("");
    try {
      await mutations.remove.mutateAsync(selected.id);
      const next = items.find((item) => item.id !== selected.id) ?? null;
      setSelectedId(next?.id ?? null);
      setDraft(next ? draftFrom(next) : { ...EMPTY_DRAFT });
      resetCredentialDraft();
      notify.success({ title: "渠道已删除" });
    } catch (error) {
      setErrorMessage(formatApiError(error, "删除渠道失败"));
    }
  }

  function deleteSelected() {
    if (!selected) return;
    confirmAction({
      title: `删除 ${selected.display_name}`,
      message: "将同时删除该渠道的模型目录和访问凭据。此操作无法撤销。",
      confirmLabel: "删除渠道",
      destructive: true,
      onConfirm: performDelete,
    });
  }

  async function copyBaseUrl() {
    if (!activeDraft.base_url || !navigator.clipboard) return;
    await navigator.clipboard.writeText(activeDraft.base_url);
    notify.info({ title: "API 地址已复制" });
  }

  const showEditor = creating || selected;
  return (
    <div className={styles.channelWorkspace}>
      <ChannelRail
        channels={items}
        busy={busy}
        reorderBusy={mutations.reorder.isPending}
        query={channelQuery}
        selectedId={selected?.id ?? selectedId}
        onCreate={beginCreate}
        onQueryChange={setChannelQuery}
        onReorder={(channelIds) => void reorderChannelList(channelIds)}
        onSelect={choose}
        onToggle={toggleEnabled}
      />
      <section className={styles.channelDetail} aria-label="AI 渠道详情">
        {!showEditor ? (
          <div className={styles.emptyState} style={{ minHeight: "100%" }}>
            <ProviderMark provider="openai-compatible" size={52} />
            <strong>选择一个渠道开始配置</strong>
            <p>查看模型目录、编辑访问配置，或创建一个新的 AI 渠道。</p>
            <Button variant="primary" onClick={beginCreate}>新建渠道</Button>
          </div>
        ) : (
          <>
            <header className={styles.detailHeader}>
              <div className={styles.detailIdentity}>
                <div className={styles.detailIconAnchor}>
                  <button
                    type="button"
                    className={styles.detailIconButton}
                    aria-label="更换供应商图标"
                    aria-expanded={iconPickerOpen}
                    onClick={() => setIconPickerOpen((open) => !open)}
                  >
                    <ProviderMark provider={activeDraft.provider} icon={activeDraft.icon} size={46} />
                  </button>
                  <ProviderIconPicker
                    open={iconPickerOpen}
                    provider={activeDraft.provider}
                    value={activeDraft.icon}
                    onChange={(icon) => setDraft((current) => ({ ...current, icon }))}
                    onClose={() => setIconPickerOpen(false)}
                  />
                </div>
                <div style={{ minWidth: 0 }}>
                  <h2 className={styles.detailName}>{activeDraft.display_name || "新建渠道"}</h2>
                  <div className={styles.detailMeta}>{providerLabel(activeDraft.provider)}{selected ? ` · ${selected.id} · ${selected.models.length} 个模型 · 更新于 ${formatDate(selected.updated_at)}` : " · 尚未创建"}</div>
                </div>
              </div>
              <div className={styles.detailActions}>
                {selected && <span className={styles.destructiveAction}><Tooltip text="删除渠道"><IconButton variant="default" icon={Trash2} aria-label="删除渠道" disabled={busy} onClick={deleteSelected} style={{ color: "var(--fgColor-danger)" }} /></Tooltip></span>}
                {(creating || canSave) && <Button variant="primary" leadingVisual={Save} disabled={!canSave || busy} onClick={() => void saveAll()}>{creating ? "创建" : "保存"}</Button>}
              </div>
            </header>
            <div className={styles.detailBody}>
              <section className={styles.inlineForm} aria-label="渠道配置">
                <div className={styles.formRow}>
                  <div><div className={styles.overviewLabel}>显示名称</div><div className={styles.overviewHint}>工作台中显示的渠道名称</div></div>
                  <div className={styles.formControl}><TextInput block value={activeDraft.display_name} placeholder="例如 DeepSeek 官方" onChange={(event) => setDraft({ ...activeDraft, display_name: event.currentTarget.value })} /></div>
                </div>
                <div className={styles.formRow}>
                  <div><div className={styles.overviewLabel}>Provider</div><div className={styles.overviewHint}>服务商适配器</div></div>
                  <div className={styles.formControl}>
                    <Select block value={activeDraft.provider} onValueChange={(provider) => setDraft({ ...activeDraft, provider, base_url: PROVIDER_DEFAULT_URLS[provider] ?? null })}>
                      {PROVIDERS.map((provider) => <Select.Option key={provider.value} value={provider.value}>{provider.label}</Select.Option>)}
                    </Select>
                  </div>
                </div>
                {creating && <div className={styles.formRow}>
                  <div><div className={styles.overviewLabel}>渠道 ID</div><div className={styles.overviewHint}>创建后作为策略与快照的固定标识</div></div>
                  <div className={styles.formControl}><TextInput block value={activeDraft.id} placeholder="例如 deepseek-primary" onChange={(event) => setDraft({ ...activeDraft, id: event.currentTarget.value })} /></div>
                </div>}
                <div className={styles.formRow}>
                  <div><div className={styles.overviewLabel}>Base URL</div><div className={styles.overviewHint}>Provider API 接入地址</div></div>
                  <div className={styles.inlineControlGroup}>
                    <TextInput block value={activeDraft.base_url ?? ""} placeholder="官方渠道可使用默认地址" onChange={(event) => setDraft({ ...activeDraft, base_url: event.currentTarget.value || null })} />
                    <Tooltip text="复制 API 地址"><IconButton variant="default" icon={Copy} aria-label="复制 API 地址" disabled={!activeDraft.base_url} onClick={() => void copyBaseUrl()} /></Tooltip>
                  </div>
                </div>
                <div className={styles.formRow}>
                  <div><div className={styles.overviewLabel}>API Key</div><div className={styles.overviewHint}>{selected?.has_secret ? "已保存，可查看或替换" : "保存后自动同步模型"}</div></div>
                  <div className={styles.formControl}>
                    <div className={styles.inlineControlGroup}>
                      <PasswordInput
                        classNames={{ input: styles.credentialInput }}
                        value={displayedSecret}
                        visible={secretVisible}
                        disabled={revealingSecret}
                        placeholder="输入 API Key（可稍后填写）"
                        autoComplete="off"
                        onFocus={(event) => { if (!secretRevealed && !secretDirty && selected?.has_secret) event.currentTarget.select(); }}
                        onChange={(event) => changeSecret(event.currentTarget.value)}
                        onVisibilityChange={changeSecretVisibility}
                      />
                    </div>
                    {credentialError && <div className={styles.formError} role="alert">{credentialError}</div>}
                  </div>
                </div>
                {selected && <div className={styles.formRow}>
                  <div><div className={styles.overviewLabel}>连通性检查</div><div className={styles.overviewHint}>向所选已启用模型发送一次最小请求</div></div>
                  <div className={styles.formControl}>
                    <div className={styles.connectivityControl}>
                      <Select block aria-label="连通性检查模型" value={effectiveCheckModelId} onValueChange={(value) => { setCheckModelId(value); setCheckResult(null); }}>
                        {connectivityModels.map((model) => <Select.Option key={model.id} value={model.id}>{model.id}</Select.Option>)}
                      </Select>
                      <Button variant="default" leadingVisual={PlugZap} disabled={!selected.has_secret || !connectivityModels.length || mutations.check.isPending} onClick={() => void checkConnectivity()}>
                        {mutations.check.isPending ? "检查中..." : "检查"}
                      </Button>
                    </div>
                    {checkResult && <div className={`${styles.connectivityResult} ${checkResult.success ? styles.connectivitySuccess : styles.connectivityFailure}`} role="status">
                      {checkResult.success ? <CircleCheck size={14} aria-hidden /> : <CircleX size={14} aria-hidden />} {checkResult.success ? "连接成功" : `连接失败${checkResult.error_code ? `（${checkResult.error_code}）` : ""}`}{checkResult.latency_ms != null ? ` · ${checkResult.latency_ms} ms` : ""}
                    </div>}
                  </div>
                </div>}
              </section>
              {selected && deferredSelected && <ModelCatalog
                busy={busy}
                busyModelId={busyModelId}
                channel={deferredSelected}
                filter={modelFilter}
                query={modelQuery}
                onFilterChange={setModelFilter}
                onPatch={(model, patch) => void patchModel(model, patch)}
                onQueryChange={setModelQuery}
                onSync={() => void syncModels()}
              />}
              <ErrorBanner message={errorMessage} />
            </div>
          </>
        )}
      </section>
    </div>
  );
}
