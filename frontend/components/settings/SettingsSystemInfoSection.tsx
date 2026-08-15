"use client";

import { Box, Heading, Spinner, Text } from "@/components/ui/primitives";
import {
  CheckCircleFillIcon,
  InfoIcon,
  XCircleFillIcon,
  DashIcon,
} from "@/components/ui/icons";
import { ErrorBanner } from "../ui/ErrorBanner";
import type { SystemInfoResponse } from "../../types/api";
import sxStyles from "./SettingsSystemInfoSection.sx.module.css";

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
    <Box className={["oops-card", sxStyles.sx1].filter(Boolean).join(" ")} >
      <Box className={sxStyles.sx2}>
        <InfoIcon size={16} />
        <Box>
          <Text className="oops-section-subtitle">System</Text>
          <Heading as="h3" className={["oops-section-title", sxStyles.sx3].filter(Boolean).join(" ")} >
            系统信息
          </Heading>
        </Box>
      </Box>

      <ErrorBanner message={errorMessage} />

      {isLoading ? (
        <Box className={sxStyles.sx4}>
          <Spinner size="medium" />
        </Box>
      ) : info ? (
        <Box className={sxStyles.sx5}>
          <InfoRow
            label="网关连接"
            value={
              <Box className={sxStyles.sx6}>
                <StatusDot status={info.gateway_reachable} />
                <Text className={sxStyles.sx7}>
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
                <Text className={sxStyles.sx8}>
                  {info.gateway_url}
                </Text>
              }
            />
          )}
          <InfoRow
            label="API Key"
            value={
              <Box className={sxStyles.sx9}>
                <StatusDot status={info.env_configured} />
                <Text className={sxStyles.sx10}>
                  {info.env_configured ? "已配置" : "未配置"}
                </Text>
              </Box>
            }
          />
          <InfoRow
            label="存储路径"
            value={
              <Text className={sxStyles.sx11}>
                {info.storage_path}
              </Text>
            }
          />
          <InfoRow
            label="缓存模型"
            last
            value={
              <Text className={sxStyles.sx12}>
                {info.models_count > 0
                  ? `${info.models_count} 个模型`
                  : "无缓存"}
              </Text>
            }
          />
        </Box>
      ) : (
        <Text className={sxStyles.sx13}>加载中...</Text>
      )}
    </Box>
  );
}

function InfoRow({ label, value, last }: { label: string; value: React.ReactNode; last?: boolean }) {
  return (
    <Box
      className={["oops-list-item", sxStyles.infoRow].join(" ")}
      data-last={last ? "true" : undefined}
    >
      <Text className={sxStyles.sx14}>{label}</Text>
      {value}
    </Box>
  );
}
