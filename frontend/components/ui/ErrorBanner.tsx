"use client";

import { useEffect } from "react";
import { notify } from "@/lib/notify";

type ErrorBannerProps = {
  message: string;
  marginBottom?: number;
};

export function ErrorBanner({ message, marginBottom = 3 }: ErrorBannerProps) {
  useEffect(() => {
    if (message) {
      notify.error({ title: message });
    }
  }, [message]);

  // 返回 null，因为我们不再渲染 Flash
  return null;
}
