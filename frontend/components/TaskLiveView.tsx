"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { 
  Box, 
  Heading, 
  Text, 
  Button, 
  Label, 
  Flash,
  Spinner
} from "@primer/react";
import { SyncIcon } from "@primer/octicons-react";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { LiveStreamRenderer } from "./LiveStreamRenderer";
import { InlineMath } from "react-katex";
import { MarkdownRenderer } from "./MarkdownRenderer";

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

function normalizeLatexInline(input: string): string {
  const trimmed = input.trim();
  if (trimmed.startsWith("$$") && trimmed.endsWith("$$")) {
    return trimmed.slice(2, -2).trim();
  }
  if (trimmed.startsWith("\\[") && trimmed.endsWith("\\]")) {
    return trimmed.slice(2, -2).trim();
  }
  if (trimmed.startsWith("\\(") && trimmed.endsWith("\\)")) {
    return trimmed.slice(2, -2).trim();
  }
  if (trimmed.startsWith("$") && trimmed.endsWith("$")) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

function looksLikeStandaloneMath(input: string): boolean {
  const t = input.trim();
  if (!t) return false;
  // Already delimited -> let auto-render or markdown handle it.
  if (t.includes("$") || t.includes("\\(") || t.includes("\\[") || t.includes("$$")) return false;
  // Avoid wrapping text with CJK characters; those are usually explanations.
  if (/[\u4e00-\u9fff]/.test(t)) return false;
  // TeX command hint (\frac, \sqrt, \left, ...)
  if (/\\[a-zA-Z]+/.test(t)) return true;
  // Simple math-y strings without commands (x^2, a_1, etc.) are too ambiguous; skip.
  return false;
}

export function TaskLiveView({ taskId }: { taskId: string }) {
  const [data, setData] = useState<TaskResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [progressLines, setProgressLines] = useState<string[]>([]);
  const [streamText, setStreamText] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

  const mathContainerRef = useRef<HTMLDivElement | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const streamBufferRef = useRef<string>("");
  const streamFlushTimerRef = useRef<number | null>(null);
  const hasLoadedStreamRef = useRef<boolean>(false);

  const flushStreamBuffer = useCallback(() => {
    if (!streamBufferRef.current) return;
    const chunk = streamBufferRef.current;
    streamBufferRef.current = "";
    setStreamText((prev) => {
      const next = prev + chunk;
      const MAX_CHARS = 200_000;
      return next.length > MAX_CHARS ? next.slice(next.length - MAX_CHARS) : next;
    });
  }, []);

  const loadStreamOnce = useCallback(async () => {
    try {
      const payload = await fetchJson<{ task_id: string; text?: string }>(
        `/tasks/${taskId}/stream?max_chars=200000`
      );
      const text = payload.text || "";
      streamBufferRef.current = "";
      setStreamText(text);
      hasLoadedStreamRef.current = true;
    } catch {
      // ignore: stream history is best-effort
    }
  }, [taskId]);

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
    if (status !== "failed") return;

    setIsRetrying(true);
    setError("");
    setStatusMessage("准备重试...");
    setProgressLines([]);
    streamBufferRef.current = "";
    setStreamText("");
    hasLoadedStreamRef.current = false;

    if (eventSourceRef.current) {
      try {
        eventSourceRef.current.close();
      } catch {
        // ignore
      }
      eventSourceRef.current = null;
    }

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

  useEffect(() => {
    hasLoadedStreamRef.current = false;
    void loadOnce();
    void loadStreamOnce();
  }, [loadOnce, loadStreamOnce]);

  // When navigating from the library, the route changes first and data arrives later.
  // Re-run KaTeX auto-render after task data is rendered to avoid "sometimes not rendered".
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
    if (!data) return;
    const status = data.task.status;
    const shouldConnectSse = status === "pending" || status === "processing" || !hasLoadedStreamRef.current;
    if (!shouldConnectSse) return;

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
    const es = new EventSource(`${API_BASE}/tasks/${taskId}/events`);
    eventSourceRef.current = es;

    es.addEventListener("progress", (evt) => {
      try {
        const payload = JSON.parse((evt as MessageEvent).data as string) as {
          status?: string;
          stage?: string | null;
          message?: string | null;
        };
        const message = payload.message || payload.stage || payload.status || "处理中";
        setStatusMessage(message);
        setProgressLines((prev) => {
          if (prev.length > 0 && prev[prev.length - 1] === message) return prev;
          return [...prev, message];
        });
      } catch {
        // ignore
      }
    });

    es.addEventListener("llm_delta", (evt) => {
      try {
        const payload = JSON.parse((evt as MessageEvent).data as string) as { delta?: string };
        if (!payload.delta) return;
        streamBufferRef.current += payload.delta;
        if (!streamFlushTimerRef.current) {
          streamFlushTimerRef.current = window.setTimeout(() => {
            streamFlushTimerRef.current = null;
            flushStreamBuffer();
          }, 80);
        }
      } catch {
        // ignore
      }
    });

    es.addEventListener("llm_snapshot", (evt) => {
      try {
        const payload = JSON.parse((evt as MessageEvent).data as string) as { text?: string };
        const text = payload.text || "";
        streamBufferRef.current = "";
        setStreamText(text);
        hasLoadedStreamRef.current = true;
      } catch {
        // ignore
      }
    });

    es.addEventListener("done", async () => {
      try {
        es.close();
      } catch {
        // ignore
      }
      if (eventSourceRef.current === es) {
        eventSourceRef.current = null;
      }
      flushStreamBuffer();
      await loadOnce();
    });

    es.addEventListener("error", () => {
      try {
        es.close();
      } catch {
        // ignore
      }
      if (eventSourceRef.current === es) {
        eventSourceRef.current = null;
      }
      setStatusMessage("进度流断开，可点击“查看最新状态”刷新。");
      flushStreamBuffer();
    });

    return () => {
      try {
        es.close();
      } catch {
        // ignore
      }
      if (eventSourceRef.current === es) {
        eventSourceRef.current = null;
      }
      if (streamFlushTimerRef.current) {
        window.clearTimeout(streamFlushTimerRef.current);
        streamFlushTimerRef.current = null;
      }
    };
  }, [data, flushStreamBuffer, loadOnce, taskId]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (streamFlushTimerRef.current) {
        window.clearTimeout(streamFlushTimerRef.current);
        streamFlushTimerRef.current = null;
      }
    };
  }, []);

  return (
    <Box ref={mathContainerRef} sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Task</Text>
          <Heading as="h2" sx={{ fontSize: 3 }}>任务 {taskId}</Heading>
        </Box>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          {data?.task?.status && <Label variant="secondary">状态：{data.task.status}</Label>}
          {(data?.task?.status === "pending" || data?.task?.status === "processing") && (
            <Button
              variant="danger"
              onClick={cancelTask}
              disabled={isCancelling || isLoading}
            >
              {isCancelling ? "作废中..." : "停止并作废"}
            </Button>
          )}
          {data?.task?.status === "failed" && (
            <Button
              onClick={retryTask}
              disabled={isRetrying || isLoading || isCancelling}
              leadingVisual={SyncIcon}
            >
              {isRetrying ? "重试中..." : "重试"}
            </Button>
          )}
          <Button 
            onClick={loadOnce} 
            disabled={isLoading}
            leadingVisual={SyncIcon}
          >
            {isLoading ? "刷新中..." : "查看最新状态"}
          </Button>
        </Box>
      </Box>

      <Text as="p" sx={{ fontSize: 1, color: 'fg.muted', mb: 3 }}>
        这里展示的是一次上传任务下抽取的所有题目、解答与标签，方便从题库视图跳转回原始上下文。
      </Text>

      {statusMessage && <Flash variant="success" sx={{ mb: 3 }}>{statusMessage}</Flash>}
      {error && <Flash variant="danger" sx={{ mb: 3 }}>{error}</Flash>}

      {progressLines.length > 0 && (
        <Box sx={{ p: 2, bg: 'canvas.subtle', borderRadius: 2, mb: 3 }}>
          <Text sx={{ fontWeight: 'bold', display: 'block', mb: 1 }}>进度</Text>
          <Box sx={{ whiteSpace: 'pre-wrap', fontFamily: 'mono', fontSize: 1 }}>
            {progressLines.map((line) => `• ${line}`).join("\n")}
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
        <Box sx={{ mt: 4 }}>
          <Heading as="h3" sx={{ fontSize: 2, mb: 2, borderBottom: '1px solid', borderColor: 'border.muted', pb: 1 }}>题目与解答</Heading>
          {data.task.problems.length === 0 ? (
            <Box sx={{ textAlign: 'center', p: 4, color: 'fg.muted' }}>
              <Text as="p" sx={{ fontWeight: 'bold' }}>尚未解析出题目。</Text>
              <Text as="p" sx={{ fontSize: 1 }}>如果任务仍在处理中，稍等片刻或刷新状态。</Text>
            </Box>
          ) : (
            <Box as="ul" sx={{ listStyle: 'none', p: 0, m: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
              {data.task.problems.map((problem, idx) => {
                const solution = data!.task.solutions.find((s) => s.problem_id === problem.problem_id);
                const tag = data!.task.tags.find((t) => t.problem_id === problem.problem_id);

                return (
                  <Box as="li" key={problem.problem_id} sx={{ p: 3, bg: 'canvas.subtle', borderRadius: 2 }}>
                    <Text sx={{ fontWeight: 'bold', display: 'block', mb: 2, fontSize: 2 }}>
                      {problem.question_no ? `题号 ${problem.question_no}` : `题目 ${idx + 1}`}
                    </Text>
                    
                    <Box sx={{ mb: 3 }}>
                      <MarkdownRenderer text={problem.problem_text || ""} />
                      {problem.options && problem.options.length > 0 && (
                        <Box sx={{ pl: 2, borderLeft: '2px solid', borderColor: 'border.default' }}>
                          {problem.options.map((opt) => (
                            <Box key={opt.key}>
                              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, flexWrap: 'wrap' }}>
                                <Text sx={{ fontWeight: 'bold' }}>{opt.key}.</Text>
                                {looksLikeStandaloneMath(opt.text) ? (
                                  <Box as="span" sx={{ '& .katex': { fontSize: '1.05em' } }}>
                                    <InlineMath math={normalizeLatexInline(opt.text)} />
                                  </Box>
                                ) : (
                                  <MarkdownRenderer text={opt.text || ""} />
                                )}
                              </Box>
                            </Box>
                          ))}
                        </Box>
                      )}
                    </Box>

                    {solution && (
                      <Box sx={{ mb: 2 }}>
                        <Text sx={{ fontWeight: 'bold', display: 'block' }}>答案：</Text>
                        <MarkdownRenderer text={solution.answer || ""} />
                        <Text sx={{ fontWeight: 'bold', display: 'block' }}>解析：</Text>
                        <MarkdownRenderer text={solution.explanation || ""} />
                      </Box>
                    )}

                    {tag && (
                      <Box sx={{ mt: 2, pt: 2, borderTop: '1px dashed', borderColor: 'border.muted' }}>
                        <Text sx={{ fontWeight: 'bold', mr: 1 }}>知识点：</Text>
                        {tag.knowledge_points.length > 0 ? (
                          tag.knowledge_points.map(kp => <Label key={kp} variant="secondary" sx={{ mr: 1 }}>{kp}</Label>)
                        ) : (
                          <Text sx={{ color: 'fg.muted' }}>未标注</Text>
                        )}
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Box>
          )}
        </Box>
      )}

      <Box sx={{ mt: 4, pt: 3, borderTop: '1px solid', borderColor: 'border.muted', fontSize: 1 }}>
        <Link href="/" passHref legacyBehavior><Text as="a" sx={{ color: 'accent.fg', textDecoration: 'none', mr: 2, cursor: 'pointer' }}>返回采集面板</Text></Link>
        <Text sx={{ color: 'fg.muted' }}>·</Text>
        <Link href="/library" passHref legacyBehavior><Text as="a" sx={{ color: 'accent.fg', textDecoration: 'none', ml: 2, cursor: 'pointer' }}>返回题库总览</Text></Link>
      </Box>
    </Box>
  );
}
