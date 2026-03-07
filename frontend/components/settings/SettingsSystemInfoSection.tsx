"use client";

import { Box, Heading, Spinner, Text } from "@primer/react";
import {
  CheckCircleFillIcon,
  InfoIcon,
  XCircleFillIcon,
  DashIcon,
} from "@primer/octicons-react";
import { ErrorBanner } from "../ui/ErrorBanner";
import type { SystemInfoResponse } from "../../types/api";

type SettingsSystemInfoSectionProps = {
  info: SystemInfoResponse | null;
  isLoading: boolean;
  errorMessage: string;
};

function StatusDot({ status }: { status: boolean | null }) {
  if (status === null) return <DashIcon size={16} />;
  return status ? (
    <CheckCircleFillIcon size={16} fill="var(--fgColor-success)" />
  ) : (
    <XCircleFillIcon size={16} fill="var(--fgColor-danger)" />
  );
}

export function SettingsSystemInfoSection({
  info,
  isLoading,
  errorMessage,
}: SettingsSystemInfoSectionProps) {
  return (
    <Box className="oops-card" sx={{ p: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
        <InfoIcon size={16} />
        <Box>
          <Text className="oops-section-subtitle">System</Text>
          <Heading as="h3" className="oops-section-title" sx={{ m: 0, fontSize: 2 }}>
            系统信息
          </Heading>
        </Box>
      </Box>

      <ErrorBanner message={errorMessage} />

      {isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <Spinner size="medium" />
        </Box>
      ) : info ? (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0 }}>
          <InfoRow
            label="网关连接"
            value={
              <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                <StatusDot status={info.gateway_reachable} />
                <Text sx={{ fontSize: 1 }}>
                  {info.gateway_reachable === null
                    ? "未配置"
                    : info.gateway_reachable
                      ? "已连接"
                      : "无法连接"}
                </Text>
              </Box>
            }
          />
          {info.gateway_url && (
            <InfoRow
              label="网关地址"
              value={
                <Text sx={{ fontSize: 1, fontFamily: "mono" }}>
                  {info.gateway_url}
                </Text>
              }
            />
          )}
          <InfoRow
            label="API Key"
            value={
              <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                <StatusDot status={info.env_configured} />
                <Text sx={{ fontSize: 1 }}>
                  {info.env_configured ? "已配置" : "未配置"}
                </Text>
              </Box>
            }
          />
          <InfoRow
            label="存储路径"
            value={
              <Text sx={{ fontSize: 1, fontFamily: "mono" }}>
                {info.storage_path}
              </Text>
            }
          />
          <InfoRow
            label="缓存模型"
            last
            value={
              <Text sx={{ fontSize: 1 }}>
                {info.models_count > 0
                  ? `${info.models_count} 个模型`
                  : "无缓存"}
              </Text>
            }
          />
        </Box>
      ) : (
        <Text sx={{ fontSize: 1, color: "fg.muted" }}>加载中...</Text>
      )}
    </Box>
  );
}

function InfoRow({ label, value, last }: { label: string; value: React.ReactNode; last?: boolean }) {
  return (
    <Box
      className="oops-list-item"
      sx={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        px: 3,
        py: 2,
        borderBottom: last ? "none" : "1px solid",
        borderColor: "border.muted",
      }}
    >
      <Text sx={{ fontWeight: 600, fontSize: 1, color: "fg.muted" }}>{label}</Text>
      {value}
    </Box>
  );
}
