"use client";

import { useEffect, useRef } from "react";
import { notify } from "@/lib/notify";

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
      notify.success({ title: "任务完成", position: "bottom-right" });
    } else if (status === "failed") {
      notify.error({ title: statusMessage || "任务失败", position: "bottom-right" });
    } else if (status === "cancelled") {
      notify.info({ title: "任务已作废", position: "bottom-right" });
    } else {
      notify.info({ title: statusMessage, position: "bottom-right" });
    }

    lastToastMessageRef.current = statusMessage;
  }, [statusMessage, status]);

  return null;
}
