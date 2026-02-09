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
  Spinner,
  FormControl,
  TextInput,
  Textarea
} from "@primer/react";
import { SyncIcon } from "@primer/octicons-react";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { LiveStreamRenderer } from "./LiveStreamRenderer";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { ProblemContent } from "./ProblemContent";
import { deleteProblem, deleteTask, overrideProblem } from "../features/tasks";
import { TagPicker } from "./TagPicker";
import { useTagDimensions } from "../features/tags";

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
  const [progressLines, setProgressLines] = useState<string[]>([]);
  const [streamText, setStreamText] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const { effectiveDimensions: tagStyles } = useTagDimensions();
  const [editingKey, setEditingKey] = useState<string>("");
  const [editQuestionNo, setEditQuestionNo] = useState<string>("");
  const [editSource, setEditSource] = useState<string>("");
  const [editProblemText, setEditProblemText] = useState<string>("");
  const [editOptionsJson, setEditOptionsJson] = useState<string>("");
  const [editOptionsError, setEditOptionsError] = useState<string>("");
  const [editKnowledgeTags, setEditKnowledgeTags] = useState<string[]>([]);
  const [editErrorTags, setEditErrorTags] = useState<string[]>([]);
  const [editUserTags, setEditUserTags] = useState<string[]>([]);
  const [editSaving, setEditSaving] = useState(false);
  const [editMessage, setEditMessage] = useState<string>("");

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
    if (status !== "failed" && status !== "completed") return;

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

  const loadEdit = useCallback((problemId: string) => {
    if (!data) return;
    const p = data.task.problems.find((x) => x.problem_id === problemId);
    if (!p) {
      setEditMessage("题目不存在");
      return;
    }
    setEditingKey(problemId);
    setEditMessage("");
    setEditQuestionNo((p.question_no || "").toString());
    setEditSource((p.source || "").toString());
    setEditProblemText((p.problem_text || "").toString());
    const options = Array.isArray(p.options) ? p.options : [];
    if (options.length > 0) {
      const normalized = options.map((opt) => {
        const entry: { key: string; text: string; latex_blocks?: string[] } = {
          key: String(opt.key || "").trim(),
          text: String(opt.text || "").trim(),
        };
        if (Array.isArray(opt.latex_blocks) && opt.latex_blocks.length > 0) {
          entry.latex_blocks = opt.latex_blocks;
        }
        return entry;
      });
      setEditOptionsJson(JSON.stringify(normalized, null, 2));
    } else {
      setEditOptionsJson("");
    }
    setEditOptionsError("");
    setEditKnowledgeTags(Array.isArray(p.knowledge_tags) ? p.knowledge_tags : []);
    setEditErrorTags(Array.isArray(p.error_tags) ? p.error_tags : []);
    setEditUserTags(Array.isArray(p.user_tags) ? p.user_tags : []);
  }, [data]);

  const saveEdit = useCallback(async (problemId: string) => {
    if (!data) return;
    setEditSaving(true);
    setEditMessage("");
    setEditOptionsError("");
    try {
      const rawOptions = editOptionsJson.trim();
      let parsedOptions: Array<{ key: string; text: string; latex_blocks?: string[] }> = [];
      if (rawOptions) {
        let raw: Array<{ key?: string; text?: string; latex_blocks?: string[] }> = [];
        try {
          const parsed = JSON.parse(rawOptions) as Array<{ key?: string; text?: string; latex_blocks?: string[] }>;
          if (!Array.isArray(parsed)) {
            throw new Error("选项 JSON 必须是数组");
          }
          raw = parsed;
        } catch (err) {
          const message = err instanceof Error ? err.message : "选项 JSON 解析失败";
          setEditOptionsError(message);
          setEditSaving(false);
          return;
        }

        parsedOptions = raw
          .map((opt) => ({
            key: String(opt?.key || "").trim(),
            text: String(opt?.text || "").trim(),
            latex_blocks: Array.isArray(opt?.latex_blocks) ? opt!.latex_blocks : undefined,
          }))
          .filter((opt) => opt.key && opt.text);

        if (parsedOptions.length === 0) {
          setEditOptionsError("选项 JSON 为空或格式不正确");
          setEditSaving(false);
          return;
        }
      }

      await overrideProblem(taskId, problemId, {
        question_no: editQuestionNo.trim() || null,
        source: editSource.trim() || null,
        problem_text: editProblemText,
        options: parsedOptions,
        knowledge_tags: editKnowledgeTags,
        error_tags: editErrorTags,
        user_tags: editUserTags,
      });
      setEditMessage("已保存");
      setEditingKey("");
      await loadOnce();
    } catch (err) {
      setEditMessage(err instanceof Error ? err.message : "保存失败");
    } finally {
      setEditSaving(false);
    }
  }, [
    data,
    editErrorTags,
    editKnowledgeTags,
    editOptionsJson,
    editProblemText,
    editQuestionNo,
    editSource,
    editUserTags,
    loadOnce,
    taskId,
  ]);

  const copyMarkdown = useCallback(async (problemId: string) => {
    if (!data) return;
    try {
      const p = data.task.problems.find((x) => x.problem_id === problemId);
      if (!p) throw new Error("题目不存在");
      const tagResult = data.task.tags.find((x) => x.problem_id === problemId);
      const s = data.task.solutions.find((x) => x.problem_id === problemId);

      const lines: string[] = [];
      lines.push(`# ${p.question_no ? `题号 ${p.question_no}` : "题目"}`);
      if (p.source) lines.push(`来源：${p.source}`);
      lines.push("");
      lines.push("## 题干");
      lines.push(p.problem_text || "");
      lines.push("");

      const knowledgeTags = Array.isArray(p.knowledge_tags) ? p.knowledge_tags : [];
      const errorTags = Array.isArray(p.error_tags) ? p.error_tags : [];
      const userTags = Array.isArray(p.user_tags) ? p.user_tags : [];
      const aiKnowledge = tagResult?.knowledge_points || [];

      lines.push("## 标签");
      if (knowledgeTags.length) lines.push(`- 知识体系：${knowledgeTags.join("，")}`);
      if (errorTags.length) lines.push(`- 错题归因：${errorTags.join("，")}`);
      if (userTags.length) lines.push(`- 自定义：${userTags.join("，")}`);
      if (aiKnowledge.length) lines.push(`- AI 知识点：${aiKnowledge.join("，")}`);
      if (!knowledgeTags.length && !errorTags.length && !userTags.length && !aiKnowledge.length) {
        lines.push("- （无）");
      }
      lines.push("");

      if (s) {
        lines.push("## 答案");
        lines.push(s.answer || "");
        lines.push("");
        lines.push("## 解析");
        lines.push(s.explanation || "");
        lines.push("");
      }

      await navigator.clipboard.writeText(lines.join("\n"));
      setStatusMessage("已复制 Markdown");
    } catch (err) {
      setError(err instanceof Error ? err.message : "复制失败");
    }
  }, [data]);

  const removeProblem = useCallback(async (problemId: string) => {
    if (!window.confirm("确认删除这道题？")) return;
    try {
      await deleteProblem(taskId, problemId);
      await loadOnce();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }, [loadOnce, taskId]);

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
    hasLoadedStreamRef.current = false;
    void loadOnce();
    void loadStreamOnce();
  }, [loadOnce, loadStreamOnce]);

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
          {(data?.task?.status === "failed" || data?.task?.status === "completed") && (
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
          <Button
            variant="danger"
            onClick={removeTask}
            disabled={isLoading || isCancelling}
          >
            删除任务
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

                    <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 2 }}>
                      <Button size="small" onClick={() => loadEdit(problem.problem_id)}>
                        编辑
                      </Button>
                      <Button size="small" onClick={() => copyMarkdown(problem.problem_id)}>
                        复制 Markdown
                      </Button>
                      <Button size="small" variant="danger" onClick={() => removeProblem(problem.problem_id)}>
                        删除题目
                      </Button>
                    </Box>

                    {editingKey === problem.problem_id ? (
                      <Box sx={{ mb: 3, p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2, bg: 'canvas.default' }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                          <Text sx={{ fontWeight: 'bold' }}>编辑题目</Text>
                          <Button size="small" onClick={() => setEditingKey("")}>关闭</Button>
                        </Box>
                        {editMessage ? (
                          <Flash variant={editMessage === "已保存" ? "success" : "danger"} sx={{ mb: 2 }}>
                            {editMessage}
                          </Flash>
                        ) : null}
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                          <Box sx={{ display: 'grid', gridTemplateColumns: ['1fr', '1fr 1fr'], gap: 3 }}>
                            <FormControl>
                              <FormControl.Label>题号</FormControl.Label>
                              <TextInput value={editQuestionNo} onChange={(e) => setEditQuestionNo(e.target.value)} block />
                            </FormControl>
                            <FormControl>
                              <FormControl.Label>来源</FormControl.Label>
                              <TextInput value={editSource} onChange={(e) => setEditSource(e.target.value)} block />
                            </FormControl>
                          </Box>

                          <FormControl>
                            <FormControl.Label>题干</FormControl.Label>
                            <Textarea value={editProblemText} onChange={(e) => setEditProblemText(e.target.value)} block rows={6} />
                          </FormControl>

                          <FormControl>
                            <FormControl.Label>选项（JSON）</FormControl.Label>
                            <Textarea
                              value={editOptionsJson}
                              onChange={(e) => {
                                setEditOptionsJson(e.target.value);
                                if (editOptionsError) setEditOptionsError("");
                              }}
                              block
                              rows={4}
                            />
                            {editOptionsError ? (
                              <Text sx={{ color: 'danger.fg', mt: 1, display: 'block' }}>{editOptionsError}</Text>
                            ) : null}
                          </FormControl>

                          <TagPicker
                            title="知识体系"
                            dimension="knowledge"
                            value={editKnowledgeTags}
                            onChange={setEditKnowledgeTags}
                            styles={tagStyles}
                            placeholder="输入搜索，Tab 补全，Enter 选第一"
                          />
                          <TagPicker
                            title="错题归因"
                            dimension="error"
                            value={editErrorTags}
                            onChange={setEditErrorTags}
                            styles={tagStyles}
                            placeholder="输入搜索，Tab 补全，Enter 选第一"
                          />
                          <TagPicker
                            title="自定义"
                            dimension="custom"
                            value={editUserTags}
                            onChange={setEditUserTags}
                            styles={tagStyles}
                            enableRemoteSearch={false}
                            placeholder="输入后回车添加"
                          />

                          <Box sx={{ display: 'flex', gap: 2 }}>
                            <Button
                              variant="primary"
                              onClick={() => saveEdit(problem.problem_id)}
                              disabled={editSaving}
                            >
                              {editSaving ? (
                                <>
                                  <Spinner size="small" sx={{ mr: 1 }} />
                                  保存中…
                                </>
                              ) : (
                                '保存'
                              )}
                            </Button>
                          </Box>
                        </Box>
                      </Box>
                    ) : null}
                    
                    <Box
                      sx={{
                        mb: 3,
                        fontFamily: "'Times New Roman','SimSun','宋体',serif",
                        "& *": { fontFamily: "'Times New Roman','SimSun','宋体',serif" },
                      }}
                    >
                      <ProblemContent
                        problemText={problem.problem_text || ""}
                        options={problem.options}
                        itemKeyPrefix={problem.problem_id}
                        fontSize={2}
                      />
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
