"use client";

import { useEffect } from "react";
import { notify } from "@/lib/notify";

type ErrorBannerProps = {
  message: string;
  title?: string;
};

export function ErrorBanner({ message, title = "操作失败" }: ErrorBannerProps) {
  useEffect(() => {
    if (!message) return;
    notify.error({ title, description: message });
  }, [message, title]);

  return null;
}
