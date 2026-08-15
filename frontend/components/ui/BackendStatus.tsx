"use client";

import { useEffect, useMemo, useState } from "react";
import { Box, Text, Tooltip } from "@/components/ui/primitives";

import { API_BASE } from "@/lib/api";
import styles from "./BackendStatus.module.css";

type BackendStatusState = "checking" | "connected" | "disconnected";

let lastPingAt = 0;
let lastPingOk: boolean | null = null;
let inFlightPing: Promise<boolean> | null = null;

async function pingBackend(signal: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health`, {
      method: "GET",
      signal,
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

export function BackendStatus() {
  const [status, setStatus] = useState<BackendStatusState>("checking");

  const label = useMemo(() => {
    if (status === "connected") return "后端：已连接";
    if (status === "disconnected") return "后端：离线";
    return "后端：检测中";
  }, [status]);

  useEffect(() => {
    let cancelled = false;

    async function getPingResult(): Promise<boolean> {
      const now = Date.now();
      if (lastPingOk !== null && now - lastPingAt < 3_000) return lastPingOk;
      if (inFlightPing) return inFlightPing;

      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 1500);
      inFlightPing = pingBackend(controller.signal).finally(() => {
        window.clearTimeout(timeout);
        inFlightPing = null;
      });

      const ok = await inFlightPing;
      lastPingAt = Date.now();
      lastPingOk = ok;
      return ok;
    }

    async function runOnce() {
      const ok = await getPingResult();
      if (!cancelled) setStatus(ok ? "connected" : "disconnected");
    }

    void runOnce();
    const handle = window.setInterval(runOnce, 10_000);

    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, []);

  return (
    <Tooltip text={label} direction="sw">
      <Box className={styles.status} data-status={status}>
        <Box className={styles.dot} />
        <Text className={styles.label}>
          {status === "connected" ? "已连接" : status === "disconnected" ? "离线" : "检测中"}
        </Text>
      </Box>
    </Tooltip>
  );
}
