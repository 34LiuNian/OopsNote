"use client";

import { Box, Button, FormControl, Heading, Label, Text, TextInput, Spinner } from "@primer/react";
import { CheckCircleFillIcon, PlugIcon, XCircleFillIcon, ZapIcon } from "@primer/octicons-react";
import { ErrorBanner } from "../ui/ErrorBanner";
import { useEffect } from "react";
import { sileo } from "sileo";
import type { GatewaySettingsResponse, GatewayTestResponse } from "../../types/api";

type GatewayDraft = {
  base_url: string;
  api_key: string;
  default_model: string;
  temperature: string;
};

type SettingsGatewaySectionProps = {
  saved: GatewaySettingsResponse | null;
  draft: GatewayDraft;
  isDirty: boolean;
  isLoading: boolean;
  isSaving: boolean;
  isTesting: boolean;
  testResult: GatewayTestResponse | null;
  statusMessage: string;
  errorMessage: string;
  onSetDraftField: (field: keyof GatewayDraft, value: string) => void;
  onReset: () => void;
  onSave: () => void;
  onTest: () => void;
};

export function SettingsGatewaySection({
  saved,
  draft,
  isDirty,
  isLoading,
  isSaving,
  isTesting,
  testResult,
  statusMessage,
  errorMessage,
  onSetDraftField,
  onReset,
  onSave,
  onTest,
}: SettingsGatewaySectionProps) {
  useEffect(() => {
    if (statusMessage) {
      sileo.success({ title: statusMessage });
    }
  }, [statusMessage]);

  return (
    <Box className="oops-card" sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 3 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <PlugIcon size={16} />
          <Box>
            <Text className="oops-section-subtitle">Connection</Text>
            <Heading as="h3" className="oops-section-title" sx={{ m: 0, fontSize: 2 }}>
              连接配置
            </Heading>
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}>
          {isDirty && !isSaving && (
            <Box className="oops-badge oops-badge-warning">有未保存更改</Box>
          )}
          <Button
            onClick={onTest}
            disabled={isTesting || isLoading}
            leadingVisual={ZapIcon}
          >
            {isTesting ? "测试中..." : "测试连接"}
          </Button>
          <Button onClick={onReset} disabled={!isDirty || isSaving}>
            重置
          </Button>
          <Button variant="primary" onClick={onSave} disabled={!isDirty || isSaving}>
            {isSaving ? "保存中..." : "保存"}
          </Button>
        </Box>
      </Box>

      <ErrorBanner message={errorMessage} />

      {testResult && (
        <Box
          sx={{
            p: 2, mb: 3, borderRadius: "var(--oops-radius-sm)",
            bg: testResult.success ? "success.subtle" : "danger.subtle",
            display: "flex", alignItems: "center", gap: 2,
          }}
        >
          {testResult.success ? (
            <CheckCircleFillIcon size={16} />
          ) : (
            <XCircleFillIcon size={16} />
          )}
          <Text sx={{ fontSize: 1 }}>{testResult.message}</Text>
        </Box>
      )}

      {isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <Spinner size="medium" />
        </Box>
      ) : (
        <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3 }}>
          <FormControl>
            <FormControl.Label>API Base URL</FormControl.Label>
            <TextInput
              value={draft.base_url}
              onChange={(e) => onSetDraftField("base_url", e.target.value)}
              placeholder={saved?.env_base_url || "http://127.0.0.1:23333/v1"}
              block
              monospace
            />
            <FormControl.Caption>
              {saved?.env_base_url
                ? `环境变量: ${saved.env_base_url}`
                : "未通过环境变量配置"}
            </FormControl.Caption>
          </FormControl>

          <FormControl>
            <FormControl.Label>API Key</FormControl.Label>
            <TextInput
              type="password"
              value={draft.api_key}
              onChange={(e) => onSetDraftField("api_key", e.target.value)}
              placeholder={
                saved?.has_api_key
                  ? `已配置 (${saved.api_key_masked})`
                  : saved?.env_has_api_key
                    ? "已通过环境变量配置"
                    : "输入 API Key"
              }
              block
              monospace
            />
            <FormControl.Caption>
              {saved?.has_api_key
                ? `当前: ${saved.api_key_masked}`
                : saved?.env_has_api_key
                  ? "通过环境变量配置"
                  : "未配置"}
              {" · 留空不修改"}
            </FormControl.Caption>
          </FormControl>

          <FormControl>
            <FormControl.Label>默认模型</FormControl.Label>
            <TextInput
              value={draft.default_model}
              onChange={(e) => onSetDraftField("default_model", e.target.value)}
              placeholder={saved?.env_default_model || "gpt-4o-mini"}
              block
              monospace
            />
            <FormControl.Caption>
              {saved?.env_default_model
                ? `环境变量: ${saved.env_default_model}`
                : "默认: gpt-4o-mini"}
              {" · 各 Agent 可单独覆盖"}
            </FormControl.Caption>
          </FormControl>

          <FormControl>
            <FormControl.Label>默认温度</FormControl.Label>
            <TextInput
              type="number"
              value={draft.temperature}
              onChange={(e) => onSetDraftField("temperature", e.target.value)}
              placeholder={
                saved?.env_temperature != null
                  ? String(saved.env_temperature)
                  : "0.2"
              }
              block
              monospace
              min={0}
              max={2}
              step={0.1}
            />
            <FormControl.Caption>
              范围 0-2，
              {saved?.env_temperature != null
                ? `环境变量: ${saved.env_temperature}`
                : "默认: 0.2"}
              {" · 各 Agent 可单独覆盖"}
            </FormControl.Caption>
          </FormControl>
        </Box>
      )}
    </Box>
  );
}
