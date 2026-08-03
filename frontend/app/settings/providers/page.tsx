"use client";

import { useMemo, useState } from "react";
import { Badge, Checkbox, Modal, PasswordInput, Select, Switch } from "@mantine/core";
import { KeyRound, Plus, RefreshCw, Save, ShieldAlert, Trash2, Wifi } from "lucide-react";
import { useAuth } from "@/components/providers/AuthProvider";
import { Box, Button, FormControl, Heading, Spinner, Text, TextInput } from "@/components/ui/primitives";
import { useAiProfiles, useAiProviderMutations } from "@/features/settings/useAiProviders";
import type { AiProfileDraft, AiProviderProfile } from "@/features/settings/types";
import { isAdminUser } from "@/lib/auth";

const PROVIDERS = [
  { value: "deepseek", label: "DeepSeek" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google Gemini" },
  { value: "openai-compatible", label: "OpenAI Compatible" },
];

const EMPTY_DRAFT: AiProfileDraft = {
  id: "",
  display_name: "",
  provider: "deepseek",
  model: "",
  base_url: "https://api.deepseek.com/v1",
  enabled: true,
  capability: { tool_calling: true, vision: false },
};

function draftFrom(profile: AiProviderProfile): AiProfileDraft {
  return {
    id: profile.id,
    display_name: profile.display_name,
    provider: profile.provider,
    model: profile.model,
    base_url: profile.base_url,
    enabled: profile.enabled,
    capability: profile.capability,
  };
}

export default function ProviderSettingsPage() {
  const { user, loading } = useAuth();
  const profiles = useAiProfiles();
  const mutations = useAiProviderMutations();
  const items = useMemo(() => profiles.data?.items ?? [], [profiles.data]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<AiProfileDraft>(EMPTY_DRAFT);
  const [creating, setCreating] = useState(false);
  const [credentialOpen, setCredentialOpen] = useState(false);
  const [secret, setSecret] = useState("");
  const [message, setMessage] = useState("");
  const selected = items.find((item) => item.id === selectedId) ?? null;

  if (loading) return <Box sx={{ p: 4 }}><Spinner size="medium" /></Box>;
  if (!isAdminUser(user)) {
    return (
      <Box sx={{ p: 4, display: "flex", gap: 2, alignItems: "center" }}>
        <ShieldAlert size={22} />
        <Box><Heading order={2}>无权访问</Heading><Text sx={{ color: "fg.muted" }}>AI Provider 配置仅管理员可用。</Text></Box>
      </Box>
    );
  }

  function choose(profile: AiProviderProfile) {
    setCreating(false);
    setSelectedId(profile.id);
    setDraft(draftFrom(profile));
    setMessage("");
  }

  function beginCreate() {
    setCreating(true);
    setSelectedId(null);
    setDraft(EMPTY_DRAFT);
    setMessage("");
  }

  async function saveMetadata() {
    setMessage("");
    try {
      if (creating) {
        const result = await mutations.create.mutateAsync(draft);
        setCreating(false);
        setSelectedId(result.profile.id);
        setMessage("Profile 元数据已创建，请继续设置凭证并验证连接。");
        setCredentialOpen(true);
      } else if (selected) {
        const { id: _id, ...payload } = draft;
        await mutations.update.mutateAsync({ profileId: selected.id, payload });
        setMessage("Profile 元数据已保存为新版本。");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function saveCredential() {
    if (!selectedId || !secret) return;
    setMessage("");
    try {
      await mutations.credential.mutateAsync({ profileId: selectedId, secret });
      setSecret("");
      setCredentialOpen(false);
      setMessage("凭证验证成功并已切换到新 profile 版本。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "连接验证失败");
    }
  }

  async function runAction(action: () => Promise<unknown>, success: string) {
    setMessage("");
    try { await action(); setMessage(success); }
    catch (error) { setMessage(error instanceof Error ? error.message : "操作失败"); }
  }

  const busy = Object.values(mutations).some((mutation) => mutation.isPending);
  const failed = /失败|错误|无权|不可|不存在/.test(message);

  return (
    <Box sx={{ p: [3, 4], pb: ["112px", 4], display: "flex", flexDirection: "column", gap: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 3, flexWrap: "wrap" }}>
        <Box><Heading order={2}>AI Provider</Heading><Text sx={{ mt: 1, color: "fg.muted" }}>管理模型元数据、连接状态和 OopsNote vault 中的凭证。</Text></Box>
        <Button variant="primary" onClick={beginCreate}><Plus size={16} /> 新建 Profile</Button>
      </Box>

      {profiles.isLoading && <Spinner size="medium" />}
      {profiles.isError && <Text sx={{ color: "fg.danger" }}>无法加载 Provider，请确认管理员权限和后端状态。</Text>}

      <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "300px minmax(0, 1fr)"], gap: 3, alignItems: "start" }}>
        <Box sx={{ borderRight: ["none", "1px solid"], borderColor: "border.default", pr: [0, 3], display: "flex", flexDirection: "column", gap: 1 }}>
          {items.map((item) => (
            <Button key={item.id} variant={selectedId === item.id && !creating ? "secondary" : "default"} onClick={() => choose(item)} sx={{ minHeight: 72, justifyContent: "flex-start", textAlign: "left", whiteSpace: "normal" }}>
              <Box sx={{ minWidth: 0 }}>
                <Text fw={600}>{item.display_name}</Text>
                <Text sx={{ color: "fg.muted", fontSize: 1, overflowWrap: "anywhere" }}>{item.provider} · {item.model}</Text>
                <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
                  <Badge size="xs" color={item.has_secret ? "green" : "yellow"}>{item.has_secret ? "已配置" : "缺少凭证"}</Badge>
                  {item.is_default && <Badge size="xs" color="blue">默认</Badge>}
                  {item.is_ocr && <Badge size="xs" color="teal">OCR</Badge>}
                </Box>
              </Box>
            </Button>
          ))}
          {!items.length && !profiles.isLoading && <Text sx={{ color: "fg.muted" }}>还没有 Provider Profile。</Text>}
        </Box>

        <Box sx={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, alignItems: "center" }}>
            <Heading order={3}>{creating ? "新建 Profile" : selected ? selected.display_name : "选择一个 Profile"}</Heading>
            {selected?.validation && <Badge color={selected.validation.success ? "green" : "red"}>{selected.validation.success ? `连接正常 · ${selected.validation.latency_ms ?? "-"} ms` : selected.validation.error_code ?? "验证失败"}</Badge>}
          </Box>

          {(creating || selected) && <>
            <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3 }}>
              <FormControl><FormControl.Label>Profile ID</FormControl.Label><TextInput value={draft.id} onChange={(event) => setDraft({ ...draft, id: event.target.value })} disabled={!creating} block /></FormControl>
              <FormControl><FormControl.Label>显示名称</FormControl.Label><TextInput value={draft.display_name} onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} block /></FormControl>
              <FormControl><FormControl.Label>Provider</FormControl.Label><Select data={PROVIDERS} value={draft.provider} onChange={(value) => value && setDraft({ ...draft, provider: value })} /></FormControl>
              <FormControl><FormControl.Label>模型</FormControl.Label><TextInput value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })} block /></FormControl>
              <FormControl sx={{ gridColumn: ["auto", "1 / -1"] }}><FormControl.Label>Base URL</FormControl.Label><TextInput value={draft.base_url ?? ""} onChange={(event) => setDraft({ ...draft, base_url: event.target.value || null })} placeholder="官方 Provider 可留空" block /></FormControl>
            </Box>
            <Box sx={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
              <Switch label="启用" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.currentTarget.checked })} />
              <Checkbox label="Tool calling" checked={draft.capability.tool_calling} onChange={(event) => setDraft({ ...draft, capability: { ...draft.capability, tool_calling: event.currentTarget.checked } })} />
              <Checkbox label="Vision" checked={draft.capability.vision} onChange={(event) => setDraft({ ...draft, capability: { ...draft.capability, vision: event.currentTarget.checked } })} />
            </Box>
            <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
              <Button variant="primary" onClick={() => void saveMetadata()} disabled={busy || !draft.id.trim() || !draft.display_name.trim() || !draft.model.trim()}><Save size={16} /> 保存元数据</Button>
              {selected && <Button onClick={() => setCredentialOpen(true)}><KeyRound size={16} /> {selected.has_secret ? "轮换凭证" : "设置凭证"}</Button>}
              {selected?.has_secret && <Button onClick={() => void runAction(() => mutations.test.mutateAsync(selected.id), "连接验证完成。") } disabled={busy}><Wifi size={16} /> 测试连接</Button>}
              {selected?.has_secret && !selected.is_default && <Button onClick={() => void runAction(() => mutations.activate.mutateAsync(selected.id), "已设为默认，仅后续新 run 生效。") } disabled={busy}>设为默认</Button>}
              {selected?.has_secret && selected.capability.vision && !selected.is_ocr && <Button onClick={() => void runAction(() => mutations.activateOcr.mutateAsync(selected.id), "已设为 OCR Provider。") } disabled={busy}>设为 OCR</Button>}
            </Box>
            {selected && <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", pt: 2, borderTop: "1px solid", borderColor: "border.default" }}>
              {selected.has_secret && <Button variant="danger" onClick={() => window.confirm("删除该凭证？已排队或运行中的 run 会阻止此操作。") && void runAction(() => mutations.deleteCredential.mutateAsync(selected.id), "凭证已删除。") } disabled={busy}><Trash2 size={16} /> 删除凭证</Button>}
              <Button variant="danger" onClick={() => window.confirm("删除该 Profile？默认、OCR 或活动 run 使用中的 Profile 无法删除。") && void runAction(() => mutations.remove.mutateAsync(selected.id).then(() => { setSelectedId(null); }), "Profile 已删除。") } disabled={busy}><Trash2 size={16} /> 删除 Profile</Button>
              <Button onClick={() => void profiles.refetch()} disabled={profiles.isFetching}><RefreshCw size={16} /> 刷新</Button>
            </Box>}
          </>}
          {message && <Text role="status" sx={{ color: failed ? "fg.danger" : "fg.success" }}>{message}</Text>}
        </Box>
      </Box>

      <Modal opened={credentialOpen} onClose={() => { setCredentialOpen(false); setSecret(""); }} title={selected?.has_secret ? "轮换 Provider 凭证" : "设置 Provider 凭证"} centered>
        <PasswordInput label="API Key" value={secret} onChange={(event) => setSecret(event.currentTarget.value)} autoComplete="new-password" description="密钥只发送到后端 vault，验证失败不会替换当前版本。" />
        <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 2, mt: 4 }}><Button onClick={() => { setCredentialOpen(false); setSecret(""); }}>取消</Button><Button variant="primary" onClick={() => void saveCredential()} disabled={!secret || mutations.credential.isPending}>验证并保存</Button></Box>
      </Modal>
    </Box>
  );
}
