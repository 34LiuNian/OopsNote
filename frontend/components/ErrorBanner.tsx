"use client";

import { Flash } from "@primer/react";

type ErrorBannerProps = {
  message: string;
  marginBottom?: number;
};

export function ErrorBanner({ message, marginBottom = 3 }: ErrorBannerProps) {
  if (!message) return null;
  return <Flash variant="danger" sx={{ mb: marginBottom }}>{message}</Flash>;
}
