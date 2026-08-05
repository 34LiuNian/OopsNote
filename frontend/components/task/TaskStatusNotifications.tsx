"use client";

import { useEffect, useRef } from "react";
import { notify } from "@/lib/notify";

interface TaskStatusNotificationsProps {
  taskId: string;
  statusMessage: string;
  status?: string;
  progressLines: string[];
}

function ProgressMessage({ lines }: { lines: string[] }) {
  const visibleLines = lines.slice(-8);
  const displayLines = visibleLines.length > 0 ? visibleLines : ["等待进度更新..."];

  return (
    <div
      aria-live="polite"
      style={{
        maxHeight: 160,
        overflowY: "auto",
        fontFamily: "var(--font-mono)",
        fontSize: 12,
        lineHeight: 1.5,
      }}
    >
      {lines.length > displayLines.length && (
        <div style={{ color: "var(--fgColor-muted)", marginBottom: 4 }}>...</div>
      )}
      {displayLines.map((line, index) => (
        <div
          key={`${line}-${index}`}
          style={{
            color: index === displayLines.length - 1 ? "var(--fgColor-default)" : "var(--fgColor-muted)",
            overflowWrap: "anywhere",
          }}
        >
          <span style={{ color: "var(--fgColor-accent)", marginRight: 6 }}>›</span>
          {line}
        </div>
      ))}
    </div>
  );
}

export function TaskStatusNotifications({ taskId, statusMessage, status, progressLines }: TaskStatusNotificationsProps) {
  const previousStatusRef = useRef<string | undefined>(undefined);
  const initializedRef = useRef(false);
  const notificationId = `task-progress-${taskId}`;

  useEffect(() => () => {
    notify.dismiss(notificationId);
  }, [notificationId]);

  useEffect(() => {
    if (!status) return;

    if (status === "pending" || status === "processing") {
      notify.upsert({
        id: notificationId,
        title: status === "pending" ? "任务排队中" : "实时进度",
        message: <ProgressMessage lines={progressLines} />,
        position: "bottom-right",
        autoClose: false,
      });
      if (!initializedRef.current) {
        initializedRef.current = true;
        previousStatusRef.current = status;
      }
      return;
    }

    if (!initializedRef.current) {
      initializedRef.current = true;
      previousStatusRef.current = status;
      return;
    }
    if (status === previousStatusRef.current) return;
    previousStatusRef.current = status;

    if (status === "completed") {
      notify.upsert({ id: notificationId, title: "任务完成", color: "green", position: "bottom-right", autoClose: 4000 });
    } else if (status === "failed") {
      notify.upsert({
        id: notificationId,
        title: statusMessage || "任务失败",
        color: "red",
        position: "bottom-right",
        autoClose: 4000,
      });
    } else if (status === "cancelled") {
      notify.upsert({ id: notificationId, title: "任务已作废", color: "blue", position: "bottom-right", autoClose: 4000 });
    }

  }, [notificationId, progressLines, status, statusMessage]);

  return null;
}
