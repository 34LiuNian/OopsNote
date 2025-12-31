"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { 
  Box, 
  Button,
  Heading, 
  Text, 
  Label, 
  Select, 
  TextInput, 
  FormControl,
  Spinner,
  Flash,
  Textarea
} from "@primer/react";
import { useTagDimensions } from "../../features/tags";
import {
  deleteProblem as deleteProblemApi,
  deleteTask as deleteTaskApi,
  getTask,
  listProblems,
  listTasks,
  overrideProblem,
} from "../../features/tasks";
import type {
  ProblemsResponse,
  ProblemSummary,
  TaskResponse,
  TasksResponse,
  TaskSummary,
  TagDimensionStyle,
} from "../../types/api";
import { TagPicker } from "../../components/TagPicker";

const SUBJECT_OPTIONS = [
  { value: "", label: "全部学科" },
  { value: "math", label: "数学" },
  { value: "physics", label: "物理" },
  { value: "chemistry", label: "化学" },
];

export default function LibraryPage() {
  const [subject, setSubject] = useState<string>("");
  const [tag, setTag] = useState<string>("");
  const [items, setItems] = useState<ProblemSummary[]>([]);
  const [activeTasks, setActiveTasks] = useState<TaskSummary[]>([]);
  const [isLoadingActive, setIsLoadingActive] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const { effectiveDimensions: tagStyles } = useTagDimensions();

  const [editingKey, setEditingKey] = useState<string>("");
  const [editQuestionNo, setEditQuestionNo] = useState<string>("");
  const [editSource, setEditSource] = useState<string>("");
  const [editProblemText, setEditProblemText] = useState<string>("");
  const [editKnowledgeTags, setEditKnowledgeTags] = useState<string[]>([]);
  const [editErrorTags, setEditErrorTags] = useState<string[]>([]);
  const [editUserTags, setEditUserTags] = useState<string[]>([]);
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editMessage, setEditMessage] = useState<string>("");

  const activeTaskItems = useMemo(
    () => activeTasks.filter((t) => t.status === "pending" || t.status === "processing"),
    [activeTasks],
  );

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    async function loadActive() {
      setIsLoadingActive(true);
      try {
        const data = await listTasks({ active_only: true, subject: subject || undefined });
        if (!cancelled) {
          setActiveTasks(data.items);
        }
      } catch {
        // Active task list is best-effort; keep the library usable even if it fails.
      } finally {
        if (!cancelled) setIsLoadingActive(false);
      }
    }

    void loadActive();

    // Poll while active tasks exist so users can see tasks complete.
    timer = window.setInterval(() => {
      void loadActive();
    }, 1500);

    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [subject]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError("");

      try {
        const data = await listProblems({ subject: subject || undefined, tag: tag || undefined });
        if (!cancelled) {
          setItems(data.items);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载题库失败");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [subject, tag]);

  async function loadEdit(taskId: string, problemId: string) {
    const key = `${taskId}:${problemId}`;
    setEditingKey(key);
    setEditMessage("");
    setEditLoading(true);
    try {
      const data = await getTask(taskId);
      const p = data.task.problems.find((x) => x.problem_id === problemId);
      if (!p) throw new Error("题目不存在");

      setEditQuestionNo((p.question_no || "").toString());
      setEditSource((p.source || "").toString());
      setEditProblemText((p.problem_text || "").toString());
      setEditKnowledgeTags(Array.isArray(p.knowledge_tags) ? p.knowledge_tags : []);
      setEditErrorTags(Array.isArray(p.error_tags) ? p.error_tags : []);
      setEditUserTags(Array.isArray(p.user_tags) ? p.user_tags : []);
    } catch (e) {
      setEditMessage(e instanceof Error ? e.message : "加载题目失败");
    } finally {
      setEditLoading(false);
    }
  }

  async function saveEdit(taskId: string, problemId: string) {
    setEditSaving(true);
    setEditMessage("");
    try {
      await overrideProblem(taskId, problemId, {
        question_no: editQuestionNo.trim() || null,
        source: editSource.trim() || null,
        problem_text: editProblemText,
        knowledge_tags: editKnowledgeTags,
        error_tags: editErrorTags,
        user_tags: editUserTags,
      });
      setEditMessage("已保存");
      setEditingKey("");
      // Reload list
      const refreshed = await listProblems({ subject: subject || undefined, tag: tag || undefined });
      setItems(refreshed.items);
    } catch (e) {
      setEditMessage(e instanceof Error ? e.message : "保存失败");
    } finally {
      setEditSaving(false);
    }
  }

  async function deleteProblem(taskId: string, problemId: string) {
    if (!window.confirm("确认删除这道题？")) return;
    try {
      await deleteProblemApi(taskId, problemId);
      // Reload list
      const refreshed = await listProblems({ subject: subject || undefined, tag: tag || undefined });
      setItems(refreshed.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  }

  async function copyMarkdown(taskId: string, problemId: string) {
    try {
      const data = await getTask(taskId);
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
    } catch (e) {
      setError(e instanceof Error ? e.message : "复制失败");
    }
  }

  async function deleteTask(taskId: string) {
    if (!window.confirm("确认删除这个任务（将删除其所有题目）？")) return;
    try {
      await deleteTaskApi(taskId);
      // best-effort refresh active list
      const data = await listTasks({ active_only: true, subject: subject || undefined });
      setActiveTasks(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除任务失败");
    }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {/* Active Tasks */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Tasks</Text>
            <Heading as="h2" sx={{ fontSize: 3 }}>进行中的任务</Heading>
          </Box>
          {isLoadingActive ? (
            <Label variant="secondary">刷新中...</Label>
          ) : activeTaskItems.length > 0 ? (
            <Label variant="secondary">进行中 {activeTaskItems.length} 条</Label>
          ) : (
            <Label variant="secondary">暂无进行中任务</Label>
          )}
        </Box>

        {activeTaskItems.length === 0 ? (
          <Box sx={{ textAlign: 'center', p: 4, color: 'fg.muted' }}>
            <Text as="p" sx={{ fontWeight: 'bold' }}>当前没有进行中的任务。</Text>
            <Text as="p" sx={{ fontSize: 1 }}>上传后任务会出现在这里，可点击进入查看进度。</Text>
          </Box>
        ) : (
          <Box>
            <Box sx={{ display: ['none', 'grid'], gridTemplateColumns: '2fr 1fr 2fr 1fr', gap: 2, px: 2, py: 1, bg: 'canvas.subtle', fontWeight: 'bold', fontSize: 1, color: 'fg.muted' }}>
              <Text>任务</Text>
              <Text>学科 / 状态</Text>
              <Text>进度</Text>
              <Text></Text>
            </Box>
            <Box as="ul" sx={{ listStyle: 'none', p: 0, m: 0 }}>
              {activeTaskItems.map((t) => (
                <Box as="li" key={t.id} sx={{ display: ['flex', 'grid'], flexDirection: 'column', gridTemplateColumns: '2fr 1fr 2fr 1fr', gap: 2, px: 2, py: 2, borderBottom: '1px solid', borderColor: 'border.muted', alignItems: ['flex-start', 'center'] }}>
                  <Box sx={{ width: '100%' }}>
                    <Text sx={{ fontWeight: 'bold', display: 'block' }}>{t.question_no ? `题号 ${t.question_no}` : "任务"}</Text>
                    <Text sx={{ fontSize: 0, color: 'fg.muted' }}>{t.id.slice(0, 6)}</Text>
                  </Box>
                  <Box sx={{ width: '100%', display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Text sx={{ display: 'block' }}>{t.subject}</Text>
                    <Label variant="secondary">{t.status}</Label>
                  </Box>
                  <Box sx={{ width: '100%' }}>
                    <Text sx={{ fontSize: 1, color: 'fg.muted' }}>{t.stage_message || t.stage || "—"}</Text>
                  </Box>
                  <Box sx={{ width: '100%', textAlign: ['left', 'right'], mt: [2, 0] }}>
                    <Link href={`/tasks/${t.id}`} passHref legacyBehavior>
                      <Label as="a" variant="accent" sx={{ cursor: 'pointer', textDecoration: 'none' }}>查看任务</Label>
                    </Link>
                  </Box>
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </Box>

      {/* Library Filter */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Library</Text>
            <Heading as="h2" sx={{ fontSize: 3 }}>题库总览</Heading>
          </Box>
          {isLoading && <Spinner size="small" />}
          {error && <Flash variant="danger">{error}</Flash>}
        </Box>

        <Box sx={{ display: 'grid', gridTemplateColumns: ['1fr', '1fr 1fr'], gap: 3, mb: 3 }}>
          <FormControl>
            <FormControl.Label>学科筛选</FormControl.Label>
            <Select value={subject} onChange={(e) => setSubject(e.target.value)} block>
              {SUBJECT_OPTIONS.map((option) => (
                <Select.Option key={option.value || "all"} value={option.value}>
                  {option.label}
                </Select.Option>
              ))}
            </Select>
          </FormControl>
          <FormControl>
            <FormControl.Label>知识点包含</FormControl.Label>
            <TextInput 
              placeholder="例如：勾股定理" 
              value={tag} 
              onChange={(e) => setTag(e.target.value)} 
              block
            />
          </FormControl>
        </Box>

        <Text as="p" sx={{ fontSize: 1, color: 'fg.muted' }}>
          这里汇总了所有已解析题目，支持按学科与知识点初步筛选。
        </Text>
      </Box>

      {/* Results */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Results</Text>
            <Heading as="h2" sx={{ fontSize: 3 }}>当前筛选结果</Heading>
          </Box>
          <Label variant="secondary">共 {items.length} 道题</Label>
        </Box>

        {items.length === 0 ? (
          <Box sx={{ textAlign: 'center', p: 4, color: 'fg.muted' }}>
            <Text as="p" sx={{ fontWeight: 'bold' }}>暂无题目。</Text>
            <Text as="p" sx={{ fontSize: 1 }}>可以先在首页上传一张手稿图片，生成几道题后再回到这里查看。</Text>
          </Box>
        ) : (
          <Box>
            <Box sx={{ display: ['none', 'grid'], gridTemplateColumns: '2fr 1fr 2fr 1fr', gap: 2, px: 2, py: 1, bg: 'canvas.subtle', fontWeight: 'bold', fontSize: 1, color: 'fg.muted' }}>
              <Text>题目</Text>
              <Text>学科 / 年级</Text>
              <Text>标签</Text>
              <Text></Text>
            </Box>
            <Box as="ul" sx={{ listStyle: 'none', p: 0, m: 0 }}>
              {items.map((item) => (
                <Box as="li" key={`${item.task_id}-${item.problem_id}`} sx={{ px: 2, py: 2, borderBottom: '1px solid', borderColor: 'border.muted' }}>
                  <Box sx={{ display: ['flex', 'grid'], flexDirection: 'column', gridTemplateColumns: ['1fr', '2fr 1fr 2fr 1fr'], gap: 2, alignItems: ['flex-start', 'center'] }}>
                  <Box sx={{ width: '100%' }}>
                    <Text sx={{ fontWeight: 'bold', display: 'block' }}>
                      {item.question_no ? `题号 ${item.question_no}` : "题目"}
                    </Text>
                    {item.source && <Text sx={{ fontSize: 0, color: 'fg.muted', display: 'block' }}>{item.source}</Text>}
                    <Link href={`/tasks/${item.task_id}`} passHref legacyBehavior>
                        <Label as="a" variant="secondary" sx={{ cursor: 'pointer', textDecoration: 'none', mt: 1, display: 'inline-block' }}>查看任务</Label>
                    </Link>
                  </Box>
                  <Box sx={{ width: '100%', display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Text sx={{ display: 'block' }}>{item.subject}</Text>
                    {item.grade && <Label variant="secondary">{item.grade}</Label>}
                  </Box>
                  <Box sx={{ width: '100%', display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {item.knowledge_points.length === 0 && !(item.knowledge_tags?.length || item.error_tags?.length || item.user_tags?.length) ? (
                      <Text sx={{ color: 'fg.muted' }}>—</Text>
                    ) : (
                      <>
                        {(item.knowledge_tags || []).map((t) => (
                          <Label key={`k:${t}`} variant={(tagStyles.knowledge?.label_variant || 'accent') as any}>
                            {t}
                          </Label>
                        ))}
                        {(item.error_tags || []).map((t) => (
                          <Label key={`e:${t}`} variant={(tagStyles.error?.label_variant || 'danger') as any}>
                            {t}
                          </Label>
                        ))}
                        {(item.user_tags || []).map((t) => (
                          <Label key={`u:${t}`} variant={(tagStyles.custom?.label_variant || 'secondary') as any}>
                            {t}
                          </Label>
                        ))}
                        {item.knowledge_points.map((kp) => (
                          <Label key={`ai:${kp}`} variant="secondary">
                            {kp}
                          </Label>
                        ))}
                      </>
                    )}
                  </Box>
                  <Box sx={{ width: '100%', display: 'flex', justifyContent: ['flex-start', 'flex-end'], gap: 2, flexWrap: 'wrap' }}>
                    <Button size="small" onClick={() => loadEdit(item.task_id, item.problem_id)}>
                      编辑
                    </Button>
                    <Button size="small" onClick={() => copyMarkdown(item.task_id, item.problem_id)}>
                      复制 Markdown
                    </Button>
                    <Button size="small" onClick={() => deleteProblem(item.task_id, item.problem_id)}>
                      删除
                    </Button>
                  </Box>
                  </Box>

                  {editingKey === `${item.task_id}-${item.problem_id}` || editingKey === `${item.task_id}:${item.problem_id}` ? (
                    <Box sx={{ mt: 3, p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2, bg: 'canvas.subtle' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Text sx={{ fontWeight: 'bold' }}>编辑题目</Text>
                        <Button size="small" onClick={() => setEditingKey("")}>关闭</Button>
                      </Box>
                      {editMessage ? (
                        <Flash variant={editMessage === "已保存" ? "success" : "danger"} sx={{ mb: 2 }}>
                          {editMessage}
                        </Flash>
                      ) : null}
                      {editLoading ? (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                          <Spinner size="small" />
                          <Text sx={{ color: 'fg.muted' }}>加载中…</Text>
                        </Box>
                      ) : (
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
                              onClick={() => saveEdit(item.task_id, item.problem_id)}
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

                            <Button
                              variant="danger"
                              onClick={() => deleteProblem(item.task_id, item.problem_id)}
                              disabled={editSaving}
                            >
                              删除题目
                            </Button>

                            <Button
                              variant="danger"
                              onClick={() => deleteTask(item.task_id)}
                              disabled={editSaving}
                            >
                              删除任务
                            </Button>
                          </Box>
                        </Box>
                      )}
                    </Box>
                  ) : null}
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
}
