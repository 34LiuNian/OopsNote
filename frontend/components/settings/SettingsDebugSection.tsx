"use client";

import { Box, Button, Heading, Spinner, Text, ToggleSwitch } from "@/components/ui/primitives";
import { BugIcon } from "@/components/ui/icons";
import { ErrorBanner } from "../ui/ErrorBanner";
import { useEffect } from "react";
import { notify } from "@/lib/notify";
import type { DebugSettingsResponse } from "../../types/api";
import sxStyles from "./SettingsDebugSection.sx.module.css";

type SettingsDebugSectionProps = {
  settings: DebugSettingsResponse | null;
  draft: DebugSettingsResponse | null;
  isLoading: boolean;
  isSaving: boolean;
  isDirty: boolean;
  statusMessage: string;
  errorMessage: string;
  onToggle: (field: "debug_llm_payload" | "persist_tasks", value: boolean) => void;
  onReset: () => void;
  onSave: () => void;
};

export function SettingsDebugSection({
  settings,
  draft,
  isLoading,
  isSaving,
  isDirty,
  statusMessage,
  errorMessage,
  onToggle,
  onReset,
  onSave,
}: SettingsDebugSectionProps) {
  useEffect(() => {
    if (statusMessage) {
      notify.success({ title: statusMessage });
    }
  }, [statusMessage]);

  return (
    <Box className={["oops-card", sxStyles.sx1].filter(Boolean).join(" ")} >
      <Box className={sxStyles.sx2}>
        <Box className={sxStyles.sx3}>
          <BugIcon size={16} />
          <Box>
            <Text className="oops-section-subtitle">调试</Text>
            <Heading as="h3" className={["oops-section-title", sxStyles.sx4].filter(Boolean).join(" ")} >
              Debug Options
            </Heading>
          </Box>
        </Box>
        <Box className={sxStyles.sx5}>
          <Button onClick={onReset} disabled={!isDirty || isSaving || isLoading}>
            重置
          </Button>
          <Button variant="primary" onClick={onSave} disabled={!isDirty || isSaving || isLoading}>
            {isSaving ? "正在保存..." : "保存"}
          </Button>
        </Box>
      </Box>

      {isDirty && !isSaving && !isLoading && (
        <Box className={["oops-badge oops-badge-warning", sxStyles.sx6].filter(Boolean).join(" ")} >
          有未保存更改
        </Box>
      )}

      <ErrorBanner message={errorMessage} />

      {isLoading ? (
        <Box className={sxStyles.sx7}>
          <Spinner size="medium" />
        </Box>
      ) : settings && draft ? (
        <Box className={sxStyles.sx8}>
          <Box
            className={["oops-list-item", sxStyles.sx9].filter(Boolean).join(" ")}

          >
            <Box className={sxStyles.sx10}>
              <Text className={sxStyles.sx11}>LLM 调试日志</Text>
              <Text className={sxStyles.sx12}>
                Record detailed LLM requests and responses for troubleshooting.
              </Text>
            </Box>
            <ToggleSwitch
              size="small"
              checked={draft.debug_llm_payload}
              disabled={isSaving}
              className={sxStyles.sx13}
              onClick={(event) => {
                event.preventDefault();
                onToggle("debug_llm_payload", !draft.debug_llm_payload);
              }}
              aria-label="LLM 调试日志"
            />
          </Box>

          <Box
            className={["oops-list-item", sxStyles.sx14].filter(Boolean).join(" ")}

          >
            <Box className={sxStyles.sx15}>
              <Text className={sxStyles.sx16}>任务记录保留</Text>
              <Text className={sxStyles.sx17}>
                Write task results to disk so they can be replayed and recovered later.
              </Text>
            </Box>
            <ToggleSwitch
              size="small"
              checked={draft.persist_tasks}
              disabled={isSaving}
              className={sxStyles.sx18}
              onClick={(event) => {
                event.preventDefault();
                onToggle("persist_tasks", !draft.persist_tasks);
              }}
              aria-label="任务记录保留"
            />
          </Box>
        </Box>
      ) : null}
    </Box>
  );
}
