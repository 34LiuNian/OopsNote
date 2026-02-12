"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Box,
  Heading,
  Text,
  Flash,
  Spinner,
} from "@primer/react";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { LiveStreamRenderer } from "./LiveStreamRenderer";
import { TaskActions } from "./task/TaskActions";
import { TaskProblemList } from "./task/TaskProblemList";
import { deleteTask } from "../features/tasks";
import { useTagDimensions } from "../features/tags";
import { useTaskStream } from "../hooks/useTaskStream";
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

  const { streamText, progressLines: streamProgress, loadStreamOnce, resetStream } = useTaskStream({
    taskId,
    status: data?.task?.status,
    onStatusMessage: setStatusMessage,
    onDone: loadOnce,
  });

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
    if (status !== "failed" && status !== "completed") return;

    setIsRetrying(true);
    setError("");
    setStatusMessage("准备重试...");
    resetStream();

    try {
      await fetchJson<TaskResponse>(
        `/tasks/${taskId}/retry?background=true&clear_stream=true`,
        { method: "POST" }
      );
      await loadOnce();
      await loadStreamOnce();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重试失败");
    } finally {
      setIsRetrying(false);
    }
  }, [data, loadOnce, loadStreamOnce, taskId]);


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
    void loadStreamOnce();
  }, [loadOnce, loadStreamOnce, resetStream]);

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

      <Text as="p" sx={{ fontSize: 1, color: 'fg.muted', mb: 3 }}>
        这里展示的是一次上传任务下抽取的所有题目、解答与标签，方便从题库视图跳转回原始上下文。
      </Text>

      {statusMessage && <Flash variant="success" sx={{ mb: 3 }}>{statusMessage}</Flash>}
      <ErrorBanner message={error} />

      {streamProgress.length > 0 && (
        <Box sx={{ p: 2, bg: 'canvas.subtle', borderRadius: 2, mb: 3 }}>
          <Text sx={{ fontWeight: 'bold', display: 'block', mb: 1 }}>进度</Text>
          <Box sx={{ whiteSpace: 'pre-wrap', fontFamily: 'mono', fontSize: 1 }}>
            {streamProgress.map((line) => `• ${line}`).join("\n")}
          </Box>
        </Box>
      )}

      {streamText && <LiveStreamRenderer text={streamText} />}

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
