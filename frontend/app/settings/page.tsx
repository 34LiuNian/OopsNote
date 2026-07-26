"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Box, Text } from "@/components/ui/primitives";
import { PageHeader } from "@/components/layout/PageHeader";
import { SettingsPiSection } from "@/components/settings/SettingsPiSection";
import { fetchJson } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import { usePiSettings } from "@/hooks/useSettings";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = usePiSettings();
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");

  useEffect(() => {
    if (data) setDraft(String(data.pi_concurrency));
  }, [data]);

  async function save() {
    const concurrency = Number(draft);
    if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 16) {
      setStatusMessage("请输入 1 到 16 之间的整数");
      return;
    }
    setSaving(true);
    setStatusMessage("");
    try {
      await fetchJson("/settings/pi", {
        method: "PUT",
        body: JSON.stringify({ pi_concurrency: concurrency }),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.pi() });
      setStatusMessage("已保存，重启 OopsNote 后生效");
    } catch (cause) {
      setStatusMessage(cause instanceof Error ? cause.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <PageHeader title="设置" description="管理 OopsNote 的运行参数和本地配置" />
      <SettingsPiSection
        settings={data ?? null}
        draft={draft}
        isLoading={isLoading}
        isSaving={saving}
        isDirty={Boolean(data && draft !== String(data.pi_concurrency))}
        errorMessage={error instanceof Error ? error.message : error ? "设置加载失败" : ""}
        statusMessage={statusMessage}
        onChange={(value) => { setDraft(value); setStatusMessage(""); }}
        onReset={() => { setDraft(data ? String(data.pi_concurrency) : ""); setStatusMessage(""); }}
        onSave={save}
      />
      <Text sx={{ color: "fg.muted", fontSize: 0 }}>
        并发数越高，资源占用越大；建议根据本机内存和模型服务限流情况调整。
      </Text>
    </Box>
  );
}
