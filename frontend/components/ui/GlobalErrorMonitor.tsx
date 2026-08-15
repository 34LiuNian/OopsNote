"use client";

import { Component, useEffect, type ErrorInfo, type ReactNode } from "react";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

function errorMessage(value: unknown, fallback: string): string {
  if (value instanceof Error && value.message) return value.message;
  if (typeof value === "string" && value.trim()) return value;
  return fallback;
}

export class GlobalErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; message?: string }> {
  state: { hasError: boolean; message?: string } = { hasError: false };

  static getDerivedStateFromError(error: unknown): { hasError: boolean; message: string } {
    return { hasError: true, message: errorMessage(error, "页面遇到未处理错误，请刷新后重试。") };
  }

  componentDidCatch(error: unknown, _info: ErrorInfo): void {
    console.error("Unhandled page render error", error);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <ErrorBanner title="页面渲染失败" message={this.state.message ?? ""} />;
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
    console.error(title, errorMessage(value, fallback));
  };
  const onError = (event: ErrorEvent) => report("Unhandled page error", event.error || event.message, "页面脚本执行失败，请刷新后重试。");
  const onRejection = (event: PromiseRejectionEvent) => report("Unhandled async error", event.reason, "异步操作未完成，请重试。");
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
}
