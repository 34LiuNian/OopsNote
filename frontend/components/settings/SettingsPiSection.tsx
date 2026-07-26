"use client";

import { Box, Button, FormControl, Heading, Spinner, Text, TextInput } from "@/components/ui/primitives";
import { CpuIcon } from "@/components/ui/icons";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import type { PiSettingsResponse } from "@/types/api";

type SettingsPiSectionProps = {
  settings: PiSettingsResponse | null;
  draft: string;
  isLoading: boolean;
  isSaving: boolean;
  isDirty: boolean;
  errorMessage: string;
  statusMessage: string;
  onChange: (value: string) => void;
  onReset: () => void;
  onSave: () => void;
};

export function SettingsPiSection({
  settings,
  draft,
  isLoading,
  isSaving,
  isDirty,
  errorMessage,
  statusMessage,
  onChange,
  onReset,
  onSave,
}: SettingsPiSectionProps) {
  return (
    <Box className="oops-card" sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 3 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <CpuIcon size={16} />
          <Box>
            <Text className="oops-section-subtitle">Pi Runtime</Text>
            <Heading as="h3" className="oops-section-title" sx={{ m: 0, fontSize: 2 }}>
              Pi 并发线程
            </Heading>
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 2 }}>
          <Button onClick={onReset} disabled={!isDirty || isSaving || isLoading}>重置</Button>
          <Button variant="primary" onClick={onSave} disabled={!isDirty || isSaving || isLoading}>保存</Button>
        </Box>
      </Box>

      {isDirty && !isSaving && !isLoading && (
        <Box className="oops-badge oops-badge-warning" sx={{ mb: 3 }}>有未保存更改</Box>
      )}
      <ErrorBanner message={errorMessage} />

      {isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}><Spinner size="medium" /></Box>
      ) : (
        <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "minmax(220px, 320px) 1fr"], gap: 3, alignItems: "end" }}>
          <FormControl>
            <FormControl.Label>并发数</FormControl.Label>
            <TextInput
              type="number"
              min={1}
              max={16}
              step={1}
              value={draft}
              onChange={(event) => onChange(event.target.value)}
              block
              monospace
            />
            <FormControl.Caption>范围 1–16；保存后重启 OopsNote 生效</FormControl.Caption>
          </FormControl>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <Text sx={{ fontSize: 1, color: "fg.muted" }}>
              当前运行中的 worker：{settings?.workers ?? "—"}
            </Text>
            <Text sx={{ fontSize: 1, color: "fg.muted" }}>
              当前服务启动配置：{settings?.pi_concurrency ?? "—"}
            </Text>
          </Box>
        </Box>
      )}
      {statusMessage && <Text sx={{ mt: 3, color: "fg.success", fontSize: 1 }}>{statusMessage}</Text>}
    </Box>
  );
}
