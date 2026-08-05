"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Badge } from "@mantine/core";
import { Save, ShieldAlert } from "lucide-react";
import { useAuth } from "@/components/providers/AuthProvider";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Box, Button, Flash, FormControl, Heading, Select, Spinner, Text } from "@/components/ui/primitives";
import { useAiChannels, useAiChannelMutations } from "@/features/settings/useAiProviders";
import { flattenModels } from "@/features/settings/modelOptions";
import type { LangChainPolicy, StageSelection } from "@/features/settings/types";
import { isAdminUser } from "@/lib/auth";
import { notify } from "@/lib/notify";

const STAGES = [
  { id: "vision", label: "Vision / OCR", hint: "必须启用 Vision" },
  { id: "agent", label: "Agent", hint: "必须启用 Tool Calling" },
  { id: "review", label: "Review", hint: "必须启用 Tool Calling" },
] as const;

const EMPTY_SELECTION: StageSelection = { channel_id: "", model_id: "" };
const EMPTY_POLICY: LangChainPolicy = {
  version: 1,
  vision: EMPTY_SELECTION,
  agent: EMPTY_SELECTION,
  review: EMPTY_SELECTION,
  updated_at: null,
};

function formatUpdatedAt(updatedAt: string | null) {
  if (!updatedAt) return "未保存过";
  const date = new Date(updatedAt);
  return Number.isNaN(date.getTime()) ? updatedAt : date.toLocaleString("zh-CN");
}

export default function LangChainPolicyPage() {
  const { user, loading } = useAuth();
  const isAdmin = isAdminUser(user);
  const channels = useAiChannels(!loading && isAdmin);
  const mutations = useAiChannelMutations();
  const items = useMemo(() => channels.data?.items ?? [], [channels.data]);
  const modelOptions = useMemo(() => flattenModels(items), [items]);
  const [policyDraft, setPolicyDraft] = useState<LangChainPolicy | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  if (loading) return <Box sx={{ p: 4 }}><Spinner size="medium" /></Box>;
  if (!isAdmin) return <Box sx={{ p: 4, display: "flex", gap: 2, alignItems: "center" }}><ShieldAlert size={22} /><Box><Heading order={2}>无权访问</Heading><Text sx={{ color: "fg.muted" }}>LangChain 策略仅管理员可用。</Text></Box></Box>;

  const activePolicy = policyDraft ?? channels.data?.policy ?? EMPTY_POLICY;
  const complete = STAGES.every((stage) => activePolicy[stage.id].channel_id && activePolicy[stage.id].model_id);
  const busy = mutations.policy.isPending;

  function updateSelection(stage: typeof STAGES[number]["id"], value: string) {
    const [channel_id = "", model_id = ""] = value.split("::");
    setPolicyDraft((current) => ({ ...(current ?? EMPTY_POLICY), [stage]: { channel_id, model_id } }));
  }

  async function savePolicy() {
    if (!complete) return;
    setErrorMessage("");
    try {
      const result = await mutations.policy.mutateAsync({
        vision: activePolicy.vision,
        agent: activePolicy.agent,
        review: activePolicy.review,
      });
      setPolicyDraft(result.policy);
      notify.success({ title: "LangChain 策略已保存", description: `策略版本 ${result.policy.version} 将用于后续新 run。` });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "策略保存失败");
    }
  }

  return (
    <Box sx={{ p: [3, 4], pb: ["112px", 4], display: "flex", flexDirection: "column", gap: 4 }}>
      <Box>
        <Heading order={2}>LangChain 策略</Heading>
        <Text sx={{ mt: 1, color: "fg.muted" }}>后续新 run 使用此策略；运行中的 run 保留已冻结快照。</Text>
      </Box>
      {channels.isLoading && <Spinner size="medium" />}
      {channels.isError && <Text sx={{ color: "fg.danger" }}>无法加载渠道，请确认管理员权限和后端状态。</Text>}
      {!channels.isLoading && !channels.isError && <Box sx={{ display: "flex", flexDirection: "column", gap: 3, width: "100%" }}>
        <Box sx={{ display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" }}>
          <Badge size="sm" color="blue">策略版本 v{activePolicy.version}</Badge>
          <Text sx={{ color: "fg.muted" }}>更新于 {formatUpdatedAt(activePolicy.updated_at)}</Text>
        </Box>
        {!items.length ? <Text sx={{ color: "fg.muted" }}>请先<Link href="/settings/channels">连接渠道并同步模型</Link>。</Text> : <>
          {channels.data?.policy === null && <Flash variant="warning">策略已被清除，请重新选择三个阶段模型。</Flash>}
          {STAGES.map((stage) => {
            const current = activePolicy[stage.id];
            return <FormControl key={stage.id}>
              <FormControl.Label>{stage.label}</FormControl.Label>
              <Select value={`${current.channel_id}::${current.model_id}`} onValueChange={(value) => updateSelection(stage.id, value)}>
                <Select.Option value="">请选择模型</Select.Option>
                {modelOptions.map(({ channel, model }) => {
                  const allowed = stage.id === "vision" ? model.capability.vision : model.capability.tool_calling;
                  return <Select.Option key={`${stage.id}-${channel.id}-${model.id}`} value={`${channel.id}::${model.id}`} disabled={!allowed}>{channel.display_name} / {model.source} / {model.id}{!allowed ? "（能力未启用）" : ""}</Select.Option>;
                })}
              </Select>
              <FormControl.Caption>{stage.hint}</FormControl.Caption>
            </FormControl>;
          })}
          <Button variant="primary" onClick={() => void savePolicy()} disabled={busy || !complete}><Save size={16} /> 保存阶段策略</Button>
        </>}
      </Box>}
      <ErrorBanner message={errorMessage} />
    </Box>
  );
}
