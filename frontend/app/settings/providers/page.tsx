"use client";

import { useMemo, useState } from "react";
import { Badge, Checkbox, PasswordInput, Switch } from "@mantine/core";
import { Check, Eye, KeyRound, Plus, RefreshCw, Save, ShieldAlert, Trash2, Wrench } from "lucide-react";
import { useAuth } from "@/components/providers/AuthProvider";
import { Box, Button, FormControl, Heading, Select, Spinner, Text, TextInput } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { isAdminUser } from "@/lib/auth";
import { notify } from "@/lib/notify";
import { confirmAction } from "@/lib/confirm";
import { useAiChannels, useAiChannelMutations } from "@/features/settings/useAiProviders";
import type { ChannelDraft, ChannelModel, LangChainPolicy, ProviderChannel, StageSelection } from "@/features/settings/types";

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
  base_url: "https://api.deepseek.com/v1",
  enabled: true,
};

const STAGES = [
  { id: "vision", label: "Vision / OCR", hint: "必须启用 Vision" },
  { id: "agent", label: "Agent", hint: "必须启用 Tool Calling" },
  { id: "review", label: "Review", hint: "必须启用 Tool Calling" },
] as const;

function draftFrom(channel: ProviderChannel): ChannelDraft {
  return { id: channel.id, display_name: channel.display_name, provider: channel.provider, base_url: channel.base_url, enabled: channel.enabled };
}

function flattenModels(channels: ProviderChannel[]) {
  return channels.flatMap((channel) => channel.models.filter((model) => model.enabled).map((model) => ({ channel, model })));
}

export default function ProviderSettingsPage() {
  const { user, loading } = useAuth();
  const isAdmin = isAdminUser(user);
  const channels = useAiChannels(!loading && isAdmin);
  const mutations = useAiChannelMutations();
  const items = useMemo(() => channels.data?.items ?? [], [channels.data]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<ChannelDraft>(EMPTY_DRAFT);
  const [secret, setSecret] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [policyDraft, setPolicyDraft] = useState<LangChainPolicy | null>(null);
  const selected = items.find((item) => item.id === selectedId) ?? null;
  const modelOptions = useMemo(() => flattenModels(items), [items]);
  const activePolicy = policyDraft ?? channels.data?.policy ?? { version: 1, vision: { channel_id: "", model_id: "" }, agent: { channel_id: "", model_id: "" }, review: { channel_id: "", model_id: "" }, updated_at: null };

  if (loading) return <Box sx={{ p: 4 }}><Spinner size="medium" /></Box>;
  if (!isAdmin) return <Box sx={{ p: 4, display: "flex", gap: 2, alignItems: "center" }}><ShieldAlert size={22} /><Box><Heading order={2}>无权访问</Heading><Text sx={{ color: "fg.muted" }}>AI Provider 配置仅管理员可用。</Text></Box></Box>;

  function choose(channel: ProviderChannel) {
    setCreating(false);
    setSelectedId(channel.id);
    setDraft(draftFrom(channel));
    setSecret("");
    setErrorMessage("");
  }

  function beginCreate() {
    setCreating(true);
    setSelectedId(null);
    setDraft(EMPTY_DRAFT);
    setSecret("");
    setErrorMessage("");
  }

  async function saveChannel() {
    setErrorMessage("");
    try {
      if (creating) {
        const result = await mutations.create.mutateAsync(draft);
        setCreating(false);
        setSelectedId(result.channel.id);
        setDraft(draftFrom(result.channel));
        notify.success({ title: "渠道已创建", description: "请在右侧输入密钥，保存后会自动同步模型。" });
      } else if (selected) {
        const { id: _id, ...payload } = draft;
        const result = await mutations.update.mutateAsync({ channelId: selected.id, payload });
        notify.success({ title: "渠道元数据已保存" });
        if (result.policy_cleared) notify.warning({ title: "LangChain 策略已清除", description: "渠道已不满足现有阶段策略，请重新选择三个阶段模型。" });
      }
    } catch (error) { setErrorMessage(error instanceof Error ? error.message : "保存失败"); }
  }

  async function saveSecret() {
    if (!selected || !secret) return;
    setErrorMessage("");
    try {
      const result = await mutations.credential.mutateAsync({ channelId: selected.id, secret });
      setSecret("");
      notify.warning({ title: "模型能力需要确认", description: `已同步 ${result.discovery.count} 个模型。Tool Calling 与 Vision 默认关闭，请逐项确认。` });
      if (result.policy_cleared) notify.warning({ title: "LangChain 策略已清除", description: "新模型目录不再满足原策略，请重新选择三个阶段模型。" });
      notify.success({ title: "密钥验证成功", description: `${result.validation.message}${result.validation.latency_ms == null ? "" : ` (${result.validation.latency_ms}ms)`}` });
    } catch (error) { setErrorMessage(error instanceof Error ? error.message : "密钥验证失败"); }
  }

  async function patchModel(model: ChannelModel, patch: { enabled?: boolean; capability?: { tool_calling: boolean; vision: boolean } }) {
    if (!selected) return;
    setErrorMessage("");
    try {
      const result = await mutations.model.mutateAsync({ channelId: selected.id, modelId: model.id, payload: patch });
      if (result.policy_cleared) notify.warning({ title: "LangChain 策略已清除", description: "该模型变更使原策略不可运行，请重新选择三个阶段模型。" });
    }
    catch (error) { setErrorMessage(error instanceof Error ? error.message : "模型配置失败"); }
  }

  async function syncModels() {
    if (!selected) return;
    setErrorMessage("");
    try {
      const result = await mutations.sync.mutateAsync(selected.id);
      notify.info({ title: "模型目录已同步", description: `${result.validation.message}，已获取 ${result.discovery.count} 个模型。` });
      if (result.policy_cleared) notify.warning({ title: "LangChain 策略已清除", description: "新模型目录不再满足原策略，请重新选择三个阶段模型。" });
    } catch (error) { setErrorMessage(error instanceof Error ? error.message : "模型同步失败"); }
  }

  async function performDisableChannel() {
    if (!selected) return;
    setErrorMessage("");
    try {
      const result = await mutations.update.mutateAsync({ channelId: selected.id, payload: { ...draft, enabled: false } });
      notify.success({ title: "渠道已禁用" });
      if (result.policy_cleared) notify.warning({ title: "LangChain 策略已清除", description: "渠道已禁用，请重新选择三个阶段模型。" });
    } catch (error) { setErrorMessage(error instanceof Error ? error.message : "渠道禁用失败"); }
  }

  function disableChannel() {
    if (!selected) return;
    confirmAction({
      title: "禁用渠道",
      message: "现有 run 不受影响，后续策略不能使用该渠道。",
      confirmLabel: "禁用",
      destructive: true,
      onConfirm: performDisableChannel,
    });
  }

  function selectionFor(stage: typeof STAGES[number]["id"]): StageSelection {
    return activePolicy[stage];
  }

  async function savePolicy() {
    if (!activePolicy.vision.channel_id || !activePolicy.agent.channel_id || !activePolicy.review.channel_id) return;
    setErrorMessage("");
    try {
      const result = await mutations.policy.mutateAsync({ vision: activePolicy.vision, agent: activePolicy.agent, review: activePolicy.review });
      setPolicyDraft(result.policy);
      notify.success({ title: "LangChain 策略已保存", description: `策略版本 ${result.policy.version} 将用于后续新 run。` });
    } catch (error) { setErrorMessage(error instanceof Error ? error.message : "策略保存失败"); }
  }

  const busy = Object.values(mutations).some((mutation) => mutation.isPending);
  return (
    <Box sx={{ p: [3, 4], pb: ["112px", 4], display: "flex", flexDirection: "column", gap: 4 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", gap: 3, alignItems: "flex-start", flexWrap: "wrap" }}>
        <Box><Heading order={2}>AI Provider</Heading><Text sx={{ mt: 1, color: "fg.muted" }}>渠道、模型目录与 LangChain 三阶段策略</Text></Box>
        <Button variant="primary" onClick={beginCreate}><Plus size={16} /> 新建渠道</Button>
      </Box>
      {channels.isLoading && <Spinner size="medium" />}
      {channels.isError && <Text sx={{ color: "fg.danger" }}>无法加载渠道，请确认管理员权限和后端状态。</Text>}

      <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "280px minmax(0, 1fr)"], gap: 4, alignItems: "start" }}>
        <Box sx={{ borderRight: ["none", "1px solid"], borderColor: "border.default", pr: [0, 3], display: "flex", flexDirection: "column", gap: 1 }}>
          {items.map((channel) => <Button key={channel.id} variant={selectedId === channel.id && !creating ? "secondary" : "default"} onClick={() => choose(channel)} sx={{ minHeight: 78, justifyContent: "flex-start", textAlign: "left", whiteSpace: "normal" }}><Box sx={{ minWidth: 0 }}><Text fw={600}>{channel.display_name}</Text><Text sx={{ color: "fg.muted", fontSize: 1, overflowWrap: "anywhere" }}>{channel.provider} · {channel.models.length} 个模型</Text><Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}><Badge size="xs" color={channel.has_secret ? "green" : "yellow"}>{channel.has_secret ? "已连接" : "缺少密钥"}</Badge>{!channel.enabled && <Badge size="xs" color="gray">已禁用</Badge>}</Box></Box></Button>)}
          {!items.length && !channels.isLoading && <Text sx={{ color: "fg.muted" }}>还没有渠道。</Text>}
        </Box>

        <Box sx={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
          {(creating || selected) && <>
            <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, alignItems: "center" }}><Box><Heading order={3}>{creating ? "新建渠道" : selected?.display_name}</Heading><Text sx={{ color: "fg.muted", mt: 1 }}>密钥只进入后端 SecretStore，不会写入配置或运行记录。</Text></Box>{selected && <Switch label="启用" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.currentTarget.checked })} />}</Box>
            <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3 }}>
              <FormControl><FormControl.Label>渠道 ID</FormControl.Label><TextInput value={draft.id} onChange={(event) => setDraft({ ...draft, id: event.target.value })} disabled={!creating} block /></FormControl>
              <FormControl><FormControl.Label>显示名称</FormControl.Label><TextInput value={draft.display_name} onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} block /></FormControl>
              <FormControl><FormControl.Label>Provider 来源</FormControl.Label><Select value={draft.provider} onValueChange={(value) => setDraft({ ...draft, provider: value, base_url: PROVIDER_DEFAULT_URLS[value] ?? null })}>{PROVIDERS.map((provider) => <Select.Option key={provider.value} value={provider.value}>{provider.label}</Select.Option>)}</Select></FormControl>
              <FormControl><FormControl.Label>Base URL</FormControl.Label><TextInput value={draft.base_url ?? ""} onChange={(event) => setDraft({ ...draft, base_url: event.target.value || null })} placeholder="官方地址可使用默认值" block /></FormControl>
            </Box>
            <Box sx={{ display: "flex", gap: 2, alignItems: "end", flexWrap: "wrap" }}><FormControl sx={{ flex: 1, minWidth: 240 }}><FormControl.Label>API Key</FormControl.Label><PasswordInput value={secret} onChange={(event) => setSecret(event.currentTarget.value)} placeholder={selected?.has_secret ? "留空表示保留现有密钥" : "输入后验证并同步模型"} autoComplete="new-password" /></FormControl><Button onClick={() => void saveSecret()} disabled={!selected || !secret || busy}><KeyRound size={16} /> 验证并保存</Button></Box>
            <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}><Button variant="primary" onClick={() => void saveChannel()} disabled={busy || !draft.id.trim() || !draft.display_name.trim()}><Save size={16} /> 保存渠道</Button>{selected?.has_secret && <Button onClick={() => void syncModels()} disabled={busy}><RefreshCw size={16} /> 同步模型</Button>}</Box>
            {selected && <Box sx={{ display: "flex", flexDirection: "column", gap: 2, borderTop: "1px solid", borderColor: "border.default", pt: 3 }}><Box><Heading order={4}>模型目录</Heading><Text sx={{ color: "fg.muted", mt: 1 }}>按来源分组。新同步模型的能力默认关闭，请手动确认。</Text></Box>{Object.entries(selected.models.reduce<Record<string, ChannelModel[]>>((groups, model) => { (groups[model.source] ??= []).push(model); return groups; }, {})).map(([source, models]) => <Box key={source} sx={{ display: "flex", flexDirection: "column", gap: 1 }}><Text fw={600}>{source} <Text as="span" sx={{ color: "fg.muted" }}>({models.length})</Text></Text>{models.map((model) => <Box key={model.id} sx={{ display: "grid", gridTemplateColumns: ["1fr", "minmax(0, 1fr) auto auto auto"], gap: 2, alignItems: "center", py: 2, borderBottom: "1px solid", borderColor: "border.muted" }}><Box sx={{ minWidth: 0 }}><Text sx={{ overflowWrap: "anywhere" }}>{model.id}</Text>{!model.capability.tool_calling && !model.capability.vision && <Text sx={{ color: "fg.muted", fontSize: 1 }}>能力未确认</Text>}</Box><Checkbox label="启用" checked={model.enabled} onChange={(event) => void patchModel(model, { enabled: event.currentTarget.checked })} /><Checkbox label="Tool" checked={model.capability.tool_calling} onChange={(event) => void patchModel(model, { capability: { ...model.capability, tool_calling: event.currentTarget.checked } })} /><Checkbox label="Vision" checked={model.capability.vision} onChange={(event) => void patchModel(model, { capability: { ...model.capability, vision: event.currentTarget.checked } })} /></Box>)}</Box>)}</Box>}
            {selected && <Box sx={{ display: "flex", gap: 2, pt: 2, borderTop: "1px solid", borderColor: "border.default" }}><Button variant="danger" onClick={() => void disableChannel()} disabled={busy || !selected.enabled}><Wrench size={16} /> 禁用渠道</Button><Button onClick={() => void channels.refetch()} disabled={channels.isFetching}><RefreshCw size={16} /> 刷新</Button></Box>}
          </>}
        </Box>
      </Box>

      <Box sx={{ borderTop: "1px solid", borderColor: "border.default", pt: 4, display: "flex", flexDirection: "column", gap: 3 }}><Box><Heading order={3}>LangChain 阶段策略</Heading><Text sx={{ color: "fg.muted", mt: 1 }}>后续新 run 使用此策略；运行中的 run 保留已冻结快照。</Text></Box>{!modelOptions.length && <Text sx={{ color: "fg.muted" }}>请先连接渠道并同步模型。</Text>}{STAGES.map((stage) => { const current = selectionFor(stage.id); return <FormControl key={stage.id}><FormControl.Label>{stage.label}</FormControl.Label><Select value={`${current.channel_id}::${current.model_id}`} onValueChange={(value) => { const [channel_id, model_id] = value.split("::"); setPolicyDraft((state) => ({ ...(state ?? activePolicy), [stage.id]: { channel_id, model_id } })); }}><Select.Option value="">请选择模型</Select.Option>{modelOptions.map(({ channel, model }) => { const allowed = stage.id === "vision" ? model.capability.vision : model.capability.tool_calling; return <Select.Option key={`${stage.id}-${channel.id}-${model.id}`} value={`${channel.id}::${model.id}`} disabled={!allowed}>{channel.display_name} / {model.source} / {model.id}{!allowed ? "（能力未启用）" : ""}</Select.Option>; })}</Select><FormControl.Caption>{stage.hint}</FormControl.Caption></FormControl>; })}<Button variant="primary" onClick={() => void savePolicy()} disabled={busy}><Save size={16} /> 保存阶段策略</Button></Box>
      <ErrorBanner message={errorMessage} />
    </Box>
  );
}
