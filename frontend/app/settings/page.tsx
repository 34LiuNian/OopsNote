"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { Box, Text } from "@/components/ui/primitives";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import { SettingsRuntimeSection } from "@/components/settings/SettingsRuntimeSection";
import { useAiRuntimeSettings } from "@/hooks/useSettings";
import { fetchJson } from "@/lib/api";
import { isAdminUser } from "@/lib/auth";
import { queryKeys } from "@/lib/queryClient";

export default function SettingsPage() {
  const { user, loading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const runtime = useAiRuntimeSettings();
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const serverValue = runtime.data ? String(runtime.data.max_concurrency) : "";
  const value = draft ?? serverValue;

  async function save() {
    const maxConcurrency = Number(value);
    if (!Number.isInteger(maxConcurrency) || maxConcurrency < 1 || maxConcurrency > 16) {
      setMessage("请输入 1 到 16 之间的整数");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      await fetchJson("/settings/ai/runtime", { method: "PUT", body: JSON.stringify({ max_concurrency: maxConcurrency }) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.aiRuntime() });
      setDraft(null);
      setMessage("已保存，重启 OopsNote 后生效");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally { setSaving(false); }
  }

  if (!authLoading && !isAdminUser(user)) {
    return <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}><ShieldAlert size={20} /><Text>运行时设置仅管理员可用。</Text></Box>;
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <PageHeader title="系统运行" description="管理 OopsNote 的 AI 运行参数" />
      <SettingsRuntimeSection
        value={value}
        current={runtime.data?.max_concurrency ?? null}
        isLoading={runtime.isLoading || authLoading}
        isSaving={saving}
        isDirty={Boolean(runtime.data && draft !== null && draft !== serverValue)}
        message={runtime.error instanceof Error ? runtime.error.message : message}
        onChange={(next) => { setDraft(next); setMessage(""); }}
        onReset={() => { setDraft(null); setMessage(""); }}
        onSave={() => void save()}
      />
      <Text sx={{ color: "fg.muted", fontSize: 0 }}>并发数越高，资源占用和 Provider 限流风险越高。</Text>
    </Box>
  );
}
