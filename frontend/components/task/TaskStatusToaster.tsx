"use client";

import { useEffect, useRef } from "react";
import { sileo } from "sileo";

interface TaskStatusToasterProps {
  statusMessage: string;
  status?: string;
}

export function TaskStatusToaster({ statusMessage, status }: TaskStatusToasterProps) {
  const lastToastMessageRef = useRef<string>("");

  useEffect(() => {
    if (!statusMessage) return;
    if (statusMessage === lastToastMessageRef.current) return;

    if (status === "completed") {
      sileo.success({ title: "任务完成", position: "bottom-right" });
    } else if (status === "failed") {
      sileo.error({ title: statusMessage || "任务失败", position: "bottom-right" });
    } else if (status === "cancelled") {
      sileo.info({ title: "任务已作废", position: "bottom-right" });
    } else {
      sileo.info({ title: statusMessage, position: "bottom-right" });
    }

    lastToastMessageRef.current = statusMessage;
  }, [statusMessage, status]);

  return null;
}
