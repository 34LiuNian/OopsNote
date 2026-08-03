"use client";

import { useMemo, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { isAdminUser } from "@/lib/auth";
import { Box, Button, FormControl, Heading, Label, Spinner, Text, TextInput } from "@/components/ui/primitives";
import { useAiProfiles, useAiProviderMutations } from "@/features/settings/useAiProviders";

export default function ProviderSettingsPage() {
  const { user, loading } = useAuth();
  const admin = isAdminUser(user);
  const profiles = useAiProfiles();
  const mutations = useAiProviderMutations();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [provider, setProvider] = useState("deepseek");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com/v1");
  const [secret, setSecret] = useState("");
  const [message, setMessage] = useState("");

  const items = useMemo(() => profiles.data?.items ?? [], [profiles.data]);
  const selected = useMemo(() => items.find((item) => item.id === selectedId) ?? items[0] ?? null, [items, selectedId]);

  if (loading) return <Box sx={{ p: 4 }}><Spinner size="medium" /></Box>;
  if (!admin) {
    return <Box sx={{ p: 4 }}><Heading order={2}>无权访问</Heading><Text sx={{ mt: 2, color: "fg.muted" }}>AI Provider 配置仅管理员可用。</Text></Box>;
  }

  function selectProfile(id: string) {
    const item = items.find((profile) => profile.id === id);
    if (!item) return;
    setSelectedId(id); setDisplayName(item.id); setProvider(item.provider); setModel(item.model); setBaseUrl(item.base_url); setMessage("");
  }

  async function create() {
    setMessage("");
    try {
      await mutations.create.mutateAsync({ id: displayName.trim(), provider, model: model.trim(), base_url: baseUrl.trim(), secret });
      setSecret("");
      setMessage("Profile 已创建并完成连接验证。");
    } catch (error) { setMessage(error instanceof Error ? error.message : "创建失败"); }
  }

  async function rotate() {
    if (!selected || !secret) return;
    setMessage("");
    try {
      await mutations.rotate.mutateAsync({ profileId: selected.id, secret });
      setSecret("");
      setMessage("凭证已验证并轮换；旧凭证不会影响仍在运行的任务。");
    } catch (error) { setMessage(error instanceof Error ? error.message : "凭证更新失败"); }
  }

  return (
    <Box sx={{ p: [3, 4], display: "flex", flexDirection: "column", gap: 3 }}>
      <Box><Heading order={2}>AI Provider 配置</Heading><Text sx={{ mt: 1, color: "fg.muted" }}>密钥只提交给后端安全存储；页面不会读取、掩码或持久化密钥。</Text></Box>
      {profiles.isError && <Label variant="danger">无法加载 Provider（请确认管理员权限）</Label>}
      <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "300px minmax(0, 1fr)"], gap: 3 }}>
        <Box className="oops-card" sx={{ p: 3, display: "flex", flexDirection: "column", gap: 2 }}>
          <Heading order={3}>Profiles</Heading>
          {items.map((item) => <Button key={item.id} variant={selected?.id === item.id ? "secondary" : "default"} onClick={() => selectProfile(item.id)} sx={{ justifyContent: "flex-start", textAlign: "left", whiteSpace: "normal" }}><Box><Text fw={600}>{item.id}</Text><Text sx={{ color: "fg.muted", fontSize: 1 }}>{item.provider} · {item.model}</Text><Text sx={{ color: item.has_secret ? "fg.success" : "fg.attention", fontSize: 0 }}>{item.has_secret ? "已配置凭证" : "需要凭证"}</Text></Box></Button>)}
          {!items.length && <Text sx={{ color: "fg.muted" }}>还没有 Provider Profile。</Text>}
        </Box>
        <Box className="oops-card" sx={{ p: 3, display: "flex", flexDirection: "column", gap: 3 }}>
          <Heading order={3}>{selected ? `编辑 ${selected.id}` : "添加 Provider"}</Heading>
          <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3 }}>
            <FormControl><FormControl.Label>Profile ID</FormControl.Label><TextInput value={displayName} onChange={(event) => setDisplayName(event.target.value)} disabled={Boolean(selected)} block /></FormControl>
            <FormControl><FormControl.Label>Provider</FormControl.Label><TextInput value={provider} onChange={(event) => setProvider(event.target.value)} disabled={Boolean(selected)} block /></FormControl>
            <FormControl><FormControl.Label>模型</FormControl.Label><TextInput value={model} onChange={(event) => setModel(event.target.value)} block /></FormControl>
            <FormControl><FormControl.Label>Base URL</FormControl.Label><TextInput value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} block /></FormControl>
          </Box>
          <FormControl><FormControl.Label>新凭证</FormControl.Label><TextInput type="password" value={secret} onChange={(event) => setSecret(event.target.value)} autoComplete="new-password" block /><FormControl.Caption>仅在本次请求内存在；保存后立即清空。</FormControl.Caption></FormControl>
          <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}><Button variant="primary" onClick={() => void (selected ? rotate() : create())} disabled={!secret || mutations.create.isPending || mutations.rotate.isPending}>{selected ? "验证并轮换凭证" : "创建并验证 Profile"}</Button>{selected && <Button onClick={() => void mutations.activate.mutateAsync(selected.id).then(() => setMessage("已设为默认，后续新任务生效。")).catch((error) => setMessage(error instanceof Error ? error.message : "激活失败"))} disabled={mutations.activate.isPending || !selected.has_secret}>设为默认</Button>}</Box>
          {message && <Text sx={{ color: message.includes("失败") || message.includes("无法") ? "fg.danger" : "fg.success" }}>{message}</Text>}
        </Box>
      </Box>
    </Box>
  );
}
