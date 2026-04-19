"use client";

import { Box, Button, Heading, Spinner, Text, ToggleSwitch } from "@primer/react";
import { BugIcon } from "@primer/octicons-react";
import { ErrorBanner } from "../ui/ErrorBanner";
import { useEffect } from "react";
import { notify } from "@/lib/notify";
import type { DebugSettingsResponse } from "../../types/api";

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
    <Box className="oops-card" sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 3 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <BugIcon size={16} />
          <Box>
            <Text className="oops-section-subtitle">Debug</Text>
            <Heading as="h3" className="oops-section-title" sx={{ m: 0, fontSize: 2 }}>
              Debug Options
            </Heading>
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 2 }}>
          <Button onClick={onReset} disabled={!isDirty || isSaving || isLoading}>
            Reset
          </Button>
          <Button variant="primary" onClick={onSave} disabled={!isDirty || isSaving || isLoading}>
            {isSaving ? "Saving..." : "Save"}
          </Button>
        </Box>
      </Box>

      {isDirty && !isSaving && !isLoading && (
        <Box className="oops-badge oops-badge-warning" sx={{ mb: 3 }}>
          Unsaved changes
        </Box>
      )}

      <ErrorBanner message={errorMessage} />

      {isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <Spinner size="medium" />
        </Box>
      ) : settings && draft ? (
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
              <Text sx={{ fontWeight: 600, display: "block", fontSize: 1 }}>LLM debug log</Text>
              <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                Record detailed LLM requests and responses for troubleshooting.
              </Text>
            </Box>
            <ToggleSwitch
              size="small"
              checked={draft.debug_llm_payload}
              disabled={isSaving}
              sx={{
                "& > span[aria-hidden=\"true\"]": { display: "none" },
                "& button svg": { display: "none" },
              }}
              onClick={(event) => {
                event.preventDefault();
                onToggle("debug_llm_payload", !draft.debug_llm_payload);
              }}
              aria-label="LLM debug log"
            />
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
              <Text sx={{ fontWeight: 600, display: "block", fontSize: 1 }}>Task persistence</Text>
              <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                Write task results to disk so they can be replayed and recovered later.
              </Text>
            </Box>
            <ToggleSwitch
              size="small"
              checked={draft.persist_tasks}
              disabled={isSaving}
              sx={{
                "& > span[aria-hidden=\"true\"]": { display: "none" },
                "& button svg": { display: "none" },
              }}
              onClick={(event) => {
                event.preventDefault();
                onToggle("persist_tasks", !draft.persist_tasks);
              }}
              aria-label="Task persistence"
            />
          </Box>
        </Box>
      ) : null}
    </Box>
  );
}
