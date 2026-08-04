"use client";

import { Alert } from "@mantine/core";

type ErrorBannerProps = {
  message: string;
  marginBottom?: number;
};

export function ErrorBanner({ message, marginBottom = 3 }: ErrorBannerProps) {
  if (!message) return null;
  return <Alert color="red" title="操作失败" mb={marginBottom}>{message}</Alert>;
}
