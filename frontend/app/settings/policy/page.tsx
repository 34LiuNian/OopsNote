"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { BadgeCheck, Bot, Image, Save, ScanText, ShieldAlert } from "lucide-react";
import { useAuth } from "@/components/providers/AuthProvider";
import { Box, Button, Heading, Spinner, Text } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { isAdminUser } from "@/lib/auth";
import { notify } from "@/lib/notify";
import { useAiChannels, useAiChannelMutations } from "@/features/settings/useAiProviders";
import { policyModelUnavailableReason, updatePolicyStage } from "@/features/settings/modelOptions";
import type { LangChainPolicy, StageSelection } from "@/features/settings/types";
import { ModelPickerDrawer, PolicyStageCard, type PolicyStageDefinition } from "@/components/settings/ai";
import styles from "@/components/settings/ai/aiSettings.module.css";

const STAGES: PolicyStageDefinition[] = [
  { id: "vision", label: "Vision / OCR", hint: "图像理解与 OCR 阶段", capabilityLabel: "Vision", icon: ScanText },
  { id: "agent", label: "Agent", hint: "受限 MCP 推理阶段", capabilityLabel: "Tool Calling", icon: Bot },
  { id: "review", label: "Review", hint: "结果审校与质量检查", capabilityLabel: "Tool Calling", icon: BadgeCheck },
  { id: "diagram", label: "TikZ 题图重建", hint: "独立模型：TikZ 生成与视觉比较", capabilityLabel: "Vision", icon: Image },
];

const EMPTY_SELECTION: StageSelection = { channel_id: "", model_id: "" };
const EMPTY_POLICY: LangChainPolicy = {
  version: 1,
  vision: EMPTY_SELECTION,
  agent: EMPTY_SELECTION,
  review: EMPTY_SELECTION,
  diagram: EMPTY_SELECTION,
  updated_at: null,
};

const subscribeToHydration = () => () => undefined;
const getHydratedSnapshot = () => true;
const getServerHydrationSnapshot = () => false;

function formatUpdatedAt(updatedAt: string | null) {
  if (!updatedAt) return "未保存";
  const date = new Date(updatedAt);
  return Number.isNaN(date.getTime()) ? updatedAt : date.toLocaleString("zh-CN");
}

function sameSelections(left: LangChainPolicy, right: LangChainPolicy): boolean {
  return STAGES.every((stage) => (
    left[stage.id].channel_id === right[stage.id].channel_id
    && left[stage.id].model_id === right[stage.id].model_id
  ));
}

export default function LangChainPolicyPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const isHydrated = useSyncExternalStore(
    subscribeToHydration,
    getHydratedSnapshot,
    getServerHydrationSnapshot,
  );
  const isAdmin = isAdminUser(user);
  const channels = useAiChannels(isHydrated && !loading && isAdmin);
  const mutations = useAiChannelMutations();
  const items = useMemo(() => channels.data?.items ?? [], [channels.data]);
  const serverPolicy = channels.data?.policy ?? EMPTY_POLICY;
  const [policyDraft, setPolicyDraft] = useState<LangChainPolicy | null>(null);
  const [pickerStage, setPickerStage] = useState<PolicyStageDefinition | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  // Auth and React Query can be initialized from browser-only session/cache
  // state. Keep the SSR tree and the first client tree identical.
  if (!isHydrated || loading) return <Box sx={{ p: 4 }}><Spinner size="medium" /></Box>;
  if (!isAdmin) return <Box sx={{ p: 4, display: "flex", gap: 2, alignItems: "center" }}><ShieldAlert size={22} /><Box><Heading order={2}>无权访问</Heading><Text sx={{ color: "fg.muted" }}>LangChain 策略仅管理员可用。</Text></Box></Box>;

  const activePolicy = policyDraft ?? serverPolicy;
  const complete = STAGES.every((stage) => activePolicy[stage.id].channel_id && activePolicy[stage.id].model_id);
  const valid = STAGES.every((stage) => {
    const selection = activePolicy[stage.id];
    const channel = items.find((candidate) => candidate.id === selection.channel_id);
    const model = channel?.models.find((candidate) => candidate.id === selection.model_id);
    return Boolean(channel && model && !policyModelUnavailableReason(channel, model, stage.id));
  });
  const dirty = !sameSelections(activePolicy, serverPolicy);
  const canSave = complete && valid && dirty && !mutations.policy.isPending;

  function selectStage(stage: PolicyStageDefinition, selection: StageSelection) {
    // The server policy is the sole initial draft source. This preserves the
    // other stage selections when the first local edit is made.
    setPolicyDraft((current) => updatePolicyStage(current ?? serverPolicy, stage.id, selection));
    setErrorMessage("");
    setPickerStage(null);
  }

  async function savePolicy() {
    if (!canSave) return;
    setErrorMessage("");
    try {
      const result = await mutations.policy.mutateAsync({
        vision: activePolicy.vision,
        agent: activePolicy.agent,
        review: activePolicy.review,
        diagram: activePolicy.diagram,
      });
      setPolicyDraft(result.policy);
      notify.success({ title: "LangChain 策略已保存", description: `策略版本 ${result.policy.version} 将用于后续新 run。` });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "策略保存失败");
    }
  }

  return (
    <div className={styles.policyWorkspace}>
      <div className={styles.policyInner}>
        <header className={styles.policyHeader}>
          <div>
            <h1 className={styles.policyTitle}>AI 策略</h1>
            <div className={styles.policyDescription}>后续新 run 使用此策略；运行中的 run 保留已冻结快照。</div>
            <div className={styles.policyMeta}>
              <span>{activePolicy.updated_at ? `上次保存于 ${formatUpdatedAt(activePolicy.updated_at)}` : "尚未保存"}</span>
              {dirty && <><span className={styles.dirtyDot} aria-hidden="true" /><span>有未保存更改</span></>}
            </div>
          </div>
          <Button variant="primary" leadingVisual={Save} onClick={() => void savePolicy()} disabled={!canSave}>保存策略</Button>
        </header>

        {channels.isLoading && <Box sx={{ py: 5 }}><Spinner size="medium" /></Box>}
        {channels.isError && <Text sx={{ color: "fg.danger", mt: 4 }}>无法加载渠道，请确认管理员权限和后端状态。</Text>}
        {!channels.isLoading && !channels.isError && !items.length && (
          <div className={styles.emptyState}>
            <strong>还没有可编排的 AI 渠道</strong>
            <p>先连接渠道、保存访问凭据并同步模型，再为四个阶段选择模型。</p>
            <Button variant="primary" onClick={() => router.push("/settings/channels")}>前往 AI 渠道</Button>
          </div>
        )}
        {!channels.isLoading && !channels.isError && items.length > 0 && (
          <>
            {channels.data?.policy === null && (
              <div className={styles.emptyState} style={{ minHeight: "auto", alignItems: "flex-start", textAlign: "left", padding: "16px 0 0" }}>
                <strong>策略尚未配置</strong>
                <p>为每个阶段选择具备所需能力的已启用模型。</p>
              </div>
            )}
            <section className={styles.policyFlow} aria-label="LangChain 阶段编排">
              <div className={styles.stageNodeVision}>
                <PolicyStageCard channels={items} definition={STAGES[0]} selection={activePolicy.vision} onClick={() => setPickerStage(STAGES[0])} />
              </div>
              <div className={styles.parallelStages}>
                <div className={styles.stageNodeAgent}>
                  <PolicyStageCard channels={items} definition={STAGES[1]} selection={activePolicy.agent} onClick={() => setPickerStage(STAGES[1])} />
                </div>
                <div className={styles.stageNodeDiagram}>
                  <PolicyStageCard channels={items} definition={STAGES[3]} selection={activePolicy.diagram} onClick={() => setPickerStage(STAGES[3])} />
                </div>
              </div>
              <div className={styles.stageNodeReview}>
                <PolicyStageCard channels={items} definition={STAGES[2]} selection={activePolicy.review} onClick={() => setPickerStage(STAGES[2])} />
              </div>
            </section>
          </>
        )}
        <ErrorBanner message={errorMessage} />
      </div>
      <ModelPickerDrawer
        channels={items}
        definition={pickerStage}
        opened={Boolean(pickerStage)}
        selection={pickerStage ? activePolicy[pickerStage.id] : EMPTY_SELECTION}
        onClose={() => setPickerStage(null)}
        onSelect={(selection) => { if (pickerStage) selectStage(pickerStage, selection); }}
      />
    </div>
  );
}
