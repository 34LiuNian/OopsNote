"use client";

import { Component, useEffect, type ErrorInfo, type ReactNode } from "react";
import { notify } from "@/lib/notify";

function errorMessage(value: unknown, fallback: string): string {
  if (value instanceof Error && value.message) return value.message;
  if (typeof value === "string" && value.trim()) return value;
  return fallback;
}

export class GlobalErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, _info: ErrorInfo): void {
    notify.error({ title: "页面渲染失败", description: errorMessage(error, "页面遇到未处理错误，请刷新后重试。") });
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <div role="status" style={{ padding: "24px", color: "var(--fgColor-muted)" }}>页面当前不可用，请根据顶部错误通知处理或刷新重试。</div>;
    }
    return this.props.children;
  }
}

export function GlobalErrorMonitor() {
  useEffect(() => installGlobalErrorMonitor(), []);
  return null;
}

export function installGlobalErrorMonitor(): () => void {
  const report = (title: string, value: unknown, fallback: string) => {
    notify.error({ title, description: errorMessage(value, fallback) });
  };
  const onError = (event: ErrorEvent) => report("未处理的页面错误", event.error || event.message, "页面脚本执行失败，请刷新后重试。");
  const onRejection = (event: PromiseRejectionEvent) => report("异步操作失败", event.reason, "异步操作未完成，请重试。");
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
}
