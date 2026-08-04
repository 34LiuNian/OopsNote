"use client";

import { useEffect, useRef } from "react";
import { notify } from "@/lib/notify";

interface TaskStatusNotificationsProps {
  taskId: string;
  statusMessage: string;
  status?: string;
}

export function TaskStatusNotifications({ taskId, statusMessage, status }: TaskStatusNotificationsProps) {
  const previousStatusRef = useRef<string | undefined>(undefined);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!initializedRef.current) {
      initializedRef.current = true;
      previousStatusRef.current = status;
      return;
    }
    if (status === previousStatusRef.current) return;
    previousStatusRef.current = status;

    if (status === "completed") {
      notify.success({ id: `task-status-${taskId}`, title: "任务完成" });
    } else if (status === "failed") {
      notify.error({ id: `task-status-${taskId}`, title: statusMessage || "任务失败" });
    } else if (status === "cancelled") {
      notify.info({ id: `task-status-${taskId}`, title: "任务已作废" });
    }
  }, [status, statusMessage, taskId]);

  return null;
}
