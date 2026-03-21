"use client";

import { Box, Heading, Spinner, Text, ToggleSwitch } from "@primer/react";
import { BugIcon } from "@primer/octicons-react";
import { ErrorBanner } from "../ui/ErrorBanner";
import { useEffect } from "react";
import { notify } from "@/lib/notify";
import type { DebugSettingsResponse } from "../../types/api";

type SettingsDebugSectionProps = {
  settings: DebugSettingsResponse | null;
  isLoading: boolean;
  isSaving: boolean;
  statusMessage: string;
  errorMessage: string;
  onToggle: (field: "debug_llm_payload" | "persist_tasks", value: boolean) => void;
};

export function SettingsDebugSection({
  settings,
  isLoading,
  isSaving,
  statusMessage,
  errorMessage,
  onToggle,
}: SettingsDebugSectionProps) {
  useEffect(() => {
    if (statusMessage) {
      notify.success({ title: statusMessage });
    }
  }, [statusMessage]);

  return (
    <Box className="oops-card" sx={{ p: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
        <BugIcon size={16} />
        <Box>
          <Text className="oops-section-subtitle">Debug</Text>
          <Heading as="h3" className="oops-section-title" sx={{ m: 0, fontSize: 2 }}>
            调试选项
          </Heading>
        </Box>
      </Box>

      <ErrorBanner message={errorMessage} />

      {isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <Spinner size="medium" />
        </Box>
      ) : settings ? (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0 }}>
          <Box
            className="oops-list-item"
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              px: 3,
              py: 3,
              borderBottom: "1px solid",
              borderColor: "border.muted",
            }}
          >
            <Box sx={{ flex: 1 }}>
              <Text sx={{ fontWeight: 600, display: "block", fontSize: 1 }}>LLM 调试日志</Text>
              <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                记录所有 LLM 请求和响应的详细内容到日志文件，用于排查问题
              </Text>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
              {isSaving && <Spinner size="small" />}
              <ToggleSwitch
                size="small"
                checked={settings.debug_llm_payload}
                disabled={isSaving}
                sx={{
                  "& > span[aria-hidden=\"true\"]": { display: "none" },
                  "& button svg": { display: "none" },
                }}
                onClick={(event) => {
                  event.preventDefault();
                  onToggle("debug_llm_payload", !settings.debug_llm_payload);
                }}
                aria-label="LLM 调试日志"
              />
            </Box>
          </Box>

          <Box
            className="oops-list-item"
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              px: 3,
              py: 3,
            }}
          >
            <Box sx={{ flex: 1 }}>
              <Text sx={{ fontWeight: 600, display: "block", fontSize: 1 }}>任务持久化</Text>
              <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                将任务结果写入磁盘（关闭后任务仅存于内存，重启丢失）
              </Text>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
              {isSaving && <Spinner size="small" />}
              <ToggleSwitch
                size="small"
                checked={settings.persist_tasks}
                disabled={isSaving}
                sx={{
                  "& > span[aria-hidden=\"true\"]": { display: "none" },
                  "& button svg": { display: "none" },
                }}
                onClick={(event) => {
                  event.preventDefault();
                  onToggle("persist_tasks", !settings.persist_tasks);
                }}
                aria-label="任务持久化"
              />
            </Box>
          </Box>
        </Box>
      ) : null}
    </Box>
  );
}
