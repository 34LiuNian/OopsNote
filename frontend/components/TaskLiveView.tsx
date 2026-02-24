"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Box,
  Heading,
  Text,
  Spinner,
} from "@primer/react";
import { sileo } from "sileo";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { TaskActions } from "./task/TaskActions";
import { TaskProblemList } from "./task/TaskProblemList";
import { deleteTask } from "../features/tasks";
import { useTagDimensions } from "../features/tags";
import { useTaskStream } from "../hooks/useTaskStream";
import { useTaskProgress } from "../hooks/useTaskProgress";
import { TaskProgressBar } from "./task/TaskProgressBar";
import { ErrorBanner } from "./ErrorBanner";

type RenderMathInElement = (
  element: HTMLElement,
  options?: {
    delimiters?: Array<{ left: string; right: string; display: boolean }>;
    ignoredTags?: string[];
    ignoredClasses?: string[];
    errorCallback?: (msg: string, err: unknown) => void;
    macros?: Record<string, string>;
    throwOnError?: boolean;
    strict?: boolean | "warn" | "ignore";
    trust?: boolean | ((context: unknown) => boolean);
    output?: "html" | "mathml" | "htmlAndMathml";
    preProcess?: (math: string) => string;
  },
) => void;

export function TaskLiveView({ taskId }: { taskId: string }) {
  const [data, setData] = useState<TaskResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const { effectiveDimensions: tagStyles } = useTagDimensions();
  const [editingKey, setEditingKey] = useState<string>("");

  const mathContainerRef = useRef<HTMLDivElement | null>(null);
  const lastToastMessageRef = useRef<string>("");

  const loadOnce = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const latest = await fetchJson<TaskResponse>(`/tasks/${taskId}`);
      setData(latest);
      const msg = latest.task.stage_message || latest.task.stage || latest.task.status;
      setStatusMessage(msg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务失败");
    } finally {
      setIsLoading(false);
    }
  }, [taskId]);

  const { progressLines: streamProgress, latestTask, resetStream } = useTaskStream({
    taskId,
    status: data?.task?.status,
    onStatusMessage: setStatusMessage,
    onDone: loadOnce,
  });

  // Update data with latest task from polling
  useEffect(() => {
    if (!latestTask) return;
    setData((prev) => {
      if (!prev) return { task: latestTask };
      // Only update if something changed
      if (prev.task.status === latestTask.status &&
          prev.task.stage === latestTask.stage &&
          prev.task.stage_message === latestTask.stage_message) {
        return prev;
      }
      return { task: latestTask };
    });
  }, [latestTask]);

  const cancelTask = useCallback(async () => {
    if (!data) return;
    const status = data.task.status;
    if (status !== "pending" && status !== "processing") return;

    setIsCancelling(true);
    setError("");
    try {
      await fetchJson<TaskResponse>(`/tasks/${taskId}/cancel`, { method: "POST" });
      await loadOnce();
    } catch (err) {
      setError(err instanceof Error ? err.message : "作废任务失败");
    } finally {
      setIsCancelling(false);
    }
  }, [data, loadOnce, taskId]);

  const retryTask = useCallback(async () => {
    if (!data) return;
    const status = data.task.status;
    if (status !== "failed" && status !== "completed" && status !== "cancelled") return;

    setIsRetrying(true);
    setError("");
    setStatusMessage("准备重试...");
    resetStream();

    try {
      await fetchJson<TaskResponse>(
        `/tasks/${taskId}/retry?background=true`,
        { method: "POST" }
      );
      await loadOnce();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重试失败");
    } finally {
      setIsRetrying(false);
    }
  }, [data, loadOnce, taskId]);


  const removeTask = useCallback(async () => {
    if (!window.confirm("确认删除这个任务（将删除其所有题目）？")) return;
    try {
      await deleteTask(taskId);
      window.location.href = "/library";
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除任务失败");
    }
  }, [taskId]);

  useEffect(() => {
    resetStream();
    void loadOnce();
  }, [loadOnce, resetStream]);

  // When navigating from the library, the route changes first and data arrives later.
  // Re-run math renderer after task data is rendered to avoid "sometimes not rendered".
  useEffect(() => {
    if (!data) return;
    if (!mathContainerRef.current) return;

    let cancelled = false;
    const handle = window.setTimeout(async () => {
      try {
        const mod = (await import("katex/contrib/auto-render")) as unknown as {
          default: RenderMathInElement;
        };
        if (cancelled) return;
        mod.default(mathContainerRef.current as HTMLElement, {
          delimiters: [
            { left: "$$", right: "$$", display: true },
            { left: "\\[", right: "\\]", display: true },
            { left: "\\(", right: "\\)", display: false },
            { left: "$", right: "$", display: false },
          ],
          ignoredTags: [
            "script",
            "noscript",
            "style",
            "textarea",
            "pre",
            "code",
            "option",
          ],
          ignoredClasses: ["no-katex", "katex", "katex-display"],
          macros: {
            "\\inline": "\\displaystyle",
          },
          preProcess: (math) => `\\inline ${math}`,
          throwOnError: false,
        });
      } catch {
        // best-effort
      }
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [data]);

  useEffect(() => {
    if (!statusMessage) return;
    if (statusMessage === lastToastMessageRef.current) return;

    const status = data?.task?.status;
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
  }, [statusMessage, data?.task?.status]);

  const progressState = useTaskProgress({
    status: data?.task?.status,
    stage: data?.task?.stage,
    stageMessage: data?.task?.stage_message,
    statusMessage,
    streamProgress,
  });


  return (
    <Box ref={mathContainerRef} sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Task</Text>
          <Heading as="h2" sx={{ fontSize: 3 }}>任务 {taskId}</Heading>
        </Box>
        <TaskActions
          status={data?.task?.status}
          isCancelling={isCancelling}
          isRetrying={isRetrying}
          isLoading={isLoading}
          onCancel={cancelTask}
          onRetry={retryTask}
          onRefresh={loadOnce}
          onDelete={removeTask}
        />
      </Box>

      <TaskProgressBar
        progressState={progressState}
        latestLine={progressState.latestLine}
        error={error}
        statusMessage={statusMessage}
      />

      <ErrorBanner message={error} />

      {(data?.task?.status === "pending" || data?.task?.status === "processing") && (
        <Box
          sx={{
            position: "fixed",
            right: 24,
            bottom: 24,
            width: 320,
            maxWidth: "calc(100vw - 32px)",
            maxHeight: 240,
            overflowY: "auto",
            p: 2,
            bg: "canvas.subtle",
            borderRadius: 2,
            border: "1px solid",
            borderColor: "border.default",
            boxShadow: "shadow.large",
            zIndex: 30,
          }}
        >
          <Text sx={{ fontWeight: "bold", display: "block", mb: 1 }}>实时进度</Text>
          <Box sx={{ whiteSpace: "pre-wrap", fontFamily: "mono", fontSize: 1 }}>
            {streamProgress.length > 0
              ? streamProgress.map((line) => `• ${line}`).join("\n")
              : "• 等待进度更新..."}
          </Box>
        </Box>
      )}

      {/* LiveStreamRenderer removed - no more streaming text in polling mode */}

      {!error && !data && (
        <Box sx={{ textAlign: 'center', p: 4, color: 'fg.muted' }}>
          <Spinner size="medium" sx={{ mb: 2 }} />
          <Text as="p">正在加载任务数据...</Text>
        </Box>
      )}

      {data && (
        <TaskProblemList
          taskId={taskId}
          problems={data.task.problems}
          solutions={data.task.solutions}
          tags={data.task.tags}
          editingKey={editingKey}
          onEdit={setEditingKey}
          onCloseEdit={() => setEditingKey("")}
          onSaved={loadOnce}
          tagStyles={tagStyles}
          onStatusMessage={setStatusMessage}
          onError={setError}
        />
      )}

      <Box sx={{ mt: 4, pt: 3, borderTop: '1px solid', borderColor: 'border.muted', fontSize: 1 }}>
        <Link href="/">
          <Text as="span" sx={{ color: 'accent.fg', textDecoration: 'none', mr: 2, cursor: 'pointer' }}>返回采集面板</Text>
        </Link>
        <Text sx={{ color: 'fg.muted' }}>·</Text>
        <Link href="/library">
          <Text as="span" sx={{ color: 'accent.fg', textDecoration: 'none', ml: 2, cursor: 'pointer' }}>返回题库总览</Text>
        </Link>
      </Box>
    </Box>
  );
}
