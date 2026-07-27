"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Download, Eye, GripVertical, MoreHorizontal, Plus, Trash2, X } from "lucide-react";
import { Box, Button, FormControl, Spinner, Text, TextInput } from "@/components/ui/primitives";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProblemCard } from "@/components/ProblemCard";
import { compilePaperDraft, getPaper, listPaperCandidates, updatePaper } from "@/features/papers";
import type { PaperDraft, PaperDraftItem, ProblemSummary } from "@/types/api";
import styles from "../../paperWorkflow.module.css";

const QUESTION_TYPE_ORDER: Record<string, number> = {
  单选题: 0,
  多选题: 1,
  填空题: 2,
  解答题: 3,
};

type Candidate = ProblemSummary & { difficulty_coefficient?: number | null };

async function compileErrorMessage(response: Response): Promise<string> {
  const fallback = `试卷编译失败：${response.status}`;
  const text = await response.text();
  if (!text) return fallback;
  try {
    const payload = JSON.parse(text) as { detail?: string | { message?: string } };
    if (typeof payload.detail === "string") return payload.detail;
    return payload.detail?.message || fallback;
  } catch {
    return text;
  }
}

function storedItems(items: PaperDraftItem[]): Array<Omit<PaperDraftItem, "problem">> {
  return items.map(({ problem: _problem, ...item }) => item);
}

function difficultyLabel(value?: number | null): string {
  if (value === null || value === undefined) return "待人工处理";
  if (value <= 0.5) return `容易 ${value.toFixed(2)}`;
  if (value <= 0.8) return `适中 ${value.toFixed(2)}`;
  return `困难 ${value.toFixed(2)}`;
}

function newItemId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID().replaceAll("-", "");
  return `${Date.now()}${Math.random().toString(16).slice(2)}`;
}

function insertByDifficulty(items: PaperDraftItem[], nextItem: PaperDraftItem): PaperDraftItem[] {
  const next = [...items];
  const sameTypeIndices = next
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.question_type === nextItem.question_type);
  if (sameTypeIndices.length) {
    const coefficient = nextItem.difficulty_coefficient ?? 2;
    const before = sameTypeIndices.find(({ item }) => (item.difficulty_coefficient ?? 2) > coefficient);
    next.splice(before?.index ?? sameTypeIndices[sameTypeIndices.length - 1].index + 1, 0, nextItem);
    return next;
  }
  const order = QUESTION_TYPE_ORDER[nextItem.question_type] ?? 99;
  const beforeIndex = next.findIndex((item) => (QUESTION_TYPE_ORDER[item.question_type] ?? 99) > order);
  next.splice(beforeIndex === -1 ? next.length : beforeIndex, 0, nextItem);
  return next;
}

export default function PaperEditorPage() {
  const params = useParams<{ draftId: string }>();
  const router = useRouter();
  const draftId = params.draftId;
  const [paper, setPaper] = useState<PaperDraft | null>(null);
  const [title, setTitle] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [error, setError] = useState("");
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [pickerMode, setPickerMode] = useState<{ kind: "add" } | { kind: "replace"; itemId: string } | null>(null);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [subtitle, setSubtitle] = useState("");
  const [showAnswers, setShowAnswers] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");

  function clearFormalPreview() {
    setPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
  }

  useEffect(() => {
    let active = true;
    void getPaper(draftId)
      .then((nextPaper) => {
        if (!active) return;
        setPaper(nextPaper);
        setTitle(nextPaper.title);
        setCandidateLoading(true);
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "试卷加载失败"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [draftId]);

  useEffect(() => {
    if (!paper || title === paper.title) return;
    const timer = window.setTimeout(() => {
      void updatePaper(draftId, { title })
        .then((nextPaper) => {
          setPaper((current) => current ? { ...current, title: nextPaper.title, updated_at: nextPaper.updated_at } : nextPaper);
          setSaveState("saved");
        })
        .catch(() => setSaveState("error"));
    }, 600);
    return () => window.clearTimeout(timer);
  }, [draftId, paper, title]);

  useEffect(() => {
    if (!paper) return;
    void listPaperCandidates({
      subject: paper.subject,
      knowledgeTags: paper.knowledge_tags,
      knowledgeNodeIds: paper.knowledge_node_ids,
      limit: 500,
    })
      .then(setCandidates)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "候选题加载失败"))
      .finally(() => setCandidateLoading(false));
  }, [paper]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const usedProblemIds = useMemo(
    () => new Set(paper?.items.map((item) => item.problem_id) ?? []),
    [paper?.items],
  );
  const availableCandidates = useMemo(
    () => candidates.filter((candidate) => !usedProblemIds.has(candidate.problem_id)),
    [candidates, usedProblemIds],
  );
  const stats = useMemo(() => {
    const items = paper?.items ?? [];
    return {
      total: items.length,
      easy: items.filter((item) => item.difficulty_coefficient !== null && item.difficulty_coefficient !== undefined && item.difficulty_coefficient <= 0.5).length,
      medium: items.filter((item) => item.difficulty_coefficient !== null && item.difficulty_coefficient !== undefined && item.difficulty_coefficient > 0.5 && item.difficulty_coefficient <= 0.8).length,
      hard: items.filter((item) => item.difficulty_coefficient !== null && item.difficulty_coefficient !== undefined && item.difficulty_coefficient > 0.8).length,
    };
  }, [paper?.items]);

  async function saveItems(items: PaperDraftItem[]) {
    if (!paper) return;
    clearFormalPreview();
    setPaper({ ...paper, items });
    setSaveState("saving");
    try {
      const saved = await updatePaper(draftId, { items: storedItems(items) });
      setPaper(saved);
      setTitle(saved.title);
      setSaveState("saved");
    } catch (reason) {
      setSaveState("error");
      setError(reason instanceof Error ? reason.message : "保存失败");
    }
  }

  function chooseCandidate(candidate: Candidate) {
    if (!paper || !pickerMode) return;
    if (pickerMode.kind === "replace") {
      const next = paper.items.map((item) => item.id === pickerMode.itemId ? {
        ...item,
        task_id: candidate.task_id,
        problem_id: candidate.problem_id,
        question_type: candidate.question_type ?? "解答题",
        difficulty_coefficient: candidate.difficulty_coefficient,
        problem: candidate,
      } : item);
      setPickerMode(null);
      void saveItems(next);
      return;
    }
    const nextItem: PaperDraftItem = {
      id: newItemId(),
      task_id: candidate.task_id,
      problem_id: candidate.problem_id,
      question_type: candidate.question_type ?? "解答题",
      difficulty_coefficient: candidate.difficulty_coefficient,
      points: null,
      answer_space: "standard",
      problem: candidate,
    };
    setPickerMode(null);
    void saveItems(insertByDifficulty(paper.items, nextItem));
  }

  function dropOn(targetId: string) {
    if (!paper || !draggedId || draggedId === targetId) return;
    const sourceIndex = paper.items.findIndex((item) => item.id === draggedId);
    const targetIndex = paper.items.findIndex((item) => item.id === targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    const next = [...paper.items];
    const [moved] = next.splice(sourceIndex, 1);
    next.splice(targetIndex, 0, moved);
    setDraggedId(null);
    void saveItems(next);
  }

  function sortByDifficulty() {
    if (!paper) return;
    const next = [...paper.items].sort((left, right) => {
      const typeDelta = (QUESTION_TYPE_ORDER[left.question_type] ?? 99) - (QUESTION_TYPE_ORDER[right.question_type] ?? 99);
      if (typeDelta) return typeDelta;
      return (left.difficulty_coefficient ?? 2) - (right.difficulty_coefficient ?? 2);
    });
    void saveItems(next);
  }

  async function generateFormalPreview() {
    if (!paper || saveState !== "saved") return;
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const response = await compilePaperDraft(draftId, {
        subtitle: subtitle.trim() || undefined,
        show_answers: showAnswers,
      });
      if (!response.ok) throw new Error(await compileErrorMessage(response));
      const nextUrl = URL.createObjectURL(await response.blob());
      setPreviewUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return nextUrl;
      });
    } catch (reason) {
      setPreviewError(reason instanceof Error ? reason.message : "试卷编译失败");
    } finally {
      setPreviewLoading(false);
    }
  }

  if (loading) return <Box sx={{ p: 6, textAlign: "center" }}><Spinner /></Box>;
  if (!paper) return <Text sx={{ color: "danger.fg" }}>{error || "试卷不存在"}</Text>;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <PageHeader
        title="编辑试卷"
        description="题目内容来自题库；此处只调整试卷结构和排版属性"
        action={(
          <Box sx={{ display: "flex", gap: 2 }}>
            <Button size="small" onClick={() => router.push("/papers")}>返回草稿</Button>
            <Button
              size="small"
              leadingVisual={Eye}
              disabled={!paper.items.length || saveState !== "saved" || previewLoading}
              onClick={() => void generateFormalPreview()}
            >
              {previewLoading ? "正在编译…" : "正式预览"}
            </Button>
            <Button variant="primary" size="small" leadingVisual={Plus} onClick={() => setPickerMode({ kind: "add" })}>添加题目</Button>
          </Box>
        )}
      />

      <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "minmax(0, 1fr) auto"], gap: 2, alignItems: "end" }}>
        <FormControl>
          <FormControl.Label>试卷标题</FormControl.Label>
          <TextInput
            value={title}
            onChange={(event) => {
              clearFormalPreview();
              setTitle(event.target.value);
              setSaveState("saving");
            }}
            block
          />
        </FormControl>
        <span className={styles.saveState}>
          {saveState === "saving" ? "正在保存…" : saveState === "error" ? "保存失败" : "已自动保存"}
        </span>
      </Box>
      {error ? <Text sx={{ color: "danger.fg" }}>{error}</Text> : null}
      {previewError ? <Text sx={{ color: "danger.fg" }}>{previewError}</Text> : null}

      {previewUrl ? (
        <section className={styles.previewPanel}>
          <div className={styles.previewHeader}>
            <strong>{showAnswers ? "答案版正式预览" : "学生版正式预览"}</strong>
            <div className={styles.previewActions}>
              <a className={styles.previewDownload} href={previewUrl} download={`${paper.title || "试卷"}.pdf`}>
                <Download size={15} /> 下载 PDF
              </a>
              <button
                type="button"
                className={styles.previewClose}
                aria-label="关闭正式预览"
                onClick={clearFormalPreview}
              >
                <X size={17} />
              </button>
            </div>
          </div>
          <iframe title="试卷 PDF 正式预览" src={previewUrl} className={styles.previewFrame} />
        </section>
      ) : null}

      <div className={styles.editorGrid}>
        <div className={styles.paperList}>
          {!paper.items.length ? (
            <div className={styles.emptyPaper}>
              <Text sx={{ display: "block", fontWeight: 650 }}>这是一份空试卷</Text>
              <Text sx={{ display: "block", mt: 1 }}>点击“添加题目”，从题库手动选择。</Text>
            </div>
          ) : paper.items.map((item, index) => (
            <article
              key={item.id}
              className={`${styles.paperItem}${draggedId === item.id ? ` ${styles.paperItemDragging}` : ""}`}
              draggable
              onDragStart={() => setDraggedId(item.id)}
              onDragEnd={() => setDraggedId(null)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => dropOn(item.id)}
            >
              <button type="button" className={styles.dragHandle} aria-label={`拖动第${index + 1}题`}><GripVertical size={17} /></button>
              <div>
                <div className={styles.itemToolbar}>
                  <strong>{index + 1}. {item.question_type}</strong>
                  <span className={styles.coefficient}>{difficultyLabel(item.difficulty_coefficient)}</span>
                  <label>
                    <span className={styles.coefficient}>分值</span>{" "}
                    <input
                      className={styles.pointsInput}
                      type="number"
                      min={0}
                      value={item.points ?? ""}
                      placeholder="—"
                      onChange={(event) => {
                        const value = event.target.value === "" ? null : Math.max(0, Number(event.target.value));
                        void saveItems(paper.items.map((candidate) => candidate.id === item.id ? { ...candidate, points: value } : candidate));
                      }}
                    />
                  </label>
                  <label>
                    <span className={styles.coefficient}>答题空间</span>{" "}
                    <select
                      className={styles.pointsInput}
                      value={item.answer_space}
                      onChange={(event) => void saveItems(paper.items.map((candidate) => (
                        candidate.id === item.id ? { ...candidate, answer_space: event.target.value } : candidate
                      )))}
                    >
                      <option value="compact">紧凑</option>
                      <option value="standard">标准</option>
                      <option value="large">宽裕</option>
                    </select>
                  </label>
                  <div className={styles.itemToolbarActions}>
                    <Button size="small" onClick={() => router.push(`/tasks/${item.task_id}`)}>编辑原题</Button>
                    <Button size="small" onClick={() => setPickerMode({ kind: "replace", itemId: item.id })}>替换</Button>
                    <Button size="small" onClick={() => void saveItems(paper.items.filter((candidate) => candidate.id !== item.id))}>移除</Button>
                  </div>
                </div>
                {item.problem ? (
                  <ProblemCard
                    questionNo={item.problem.question_no}
                    questionType={item.problem.question_type}
                    source={item.problem.source}
                    problemText={item.problem.problem_text || "（无题干）"}
                    contentFormat={item.problem.content_format}
                    options={item.problem.options}
                    diagramDetected={item.problem.diagram_detected}
                    diagramKind={item.problem.diagram_kind}
                    diagramTikzSource={item.problem.diagram_tikz_source}
                    diagramSvg={item.problem.diagram_svg}
                    diagramImagePath={item.problem.diagram_image_path}
                    diagramImageTone={item.problem.diagram_image_tone}
                    diagramPosition={item.problem.diagram_position}
                    diagramScalePercent={item.problem.diagram_scale_percent}
                    diagramRenderStatus={item.problem.diagram_render_status}
                    diagramError={item.problem.diagram_error}
                    diagramNeedsReview={item.problem.diagram_needs_review}
                    itemKeyPrefix={item.problem_id}
                    showTitle={false}
                    fontSize={2}
                  />
                ) : <Text sx={{ color: "danger.fg" }}>原题已不存在，请替换或移除此题。</Text>}
              </div>
            </article>
          ))}
        </div>

        <aside className={styles.editorAside}>
          <div className={styles.asideHeader}>
            <span>{pickerMode ? (pickerMode.kind === "replace" ? "选择替换题目" : "添加题目") : "试卷结构"}</span>
            {pickerMode ? <Button size="small" onClick={() => setPickerMode(null)}>取消</Button> : null}
          </div>
          <div className={styles.asideBody}>
            {pickerMode ? (
              candidateLoading ? <Box sx={{ p: 3, textAlign: "center" }}><Spinner size="small" /></Box> : (
                <div className={styles.candidateList}>
                  {availableCandidates.map((candidate) => (
                    <button type="button" className={styles.candidate} key={candidate.problem_id} onClick={() => chooseCandidate(candidate)}>
                      <div className={styles.candidateMeta}>
                        {candidate.question_type || "题目"} · {difficultyLabel(candidate.difficulty_coefficient)}
                      </div>
                      <div className={styles.candidateText}>{candidate.problem_text || "（无题干）"}</div>
                    </button>
                  ))}
                  {!availableCandidates.length ? <Text sx={{ color: "fg.muted" }}>没有更多符合范围的题目。</Text> : null}
                </div>
              )
            ) : (
              <>
                <div className={styles.exportControls}>
                  <strong>正式导出</strong>
                  <label>
                    <span>副标题</span>
                    <input value={subtitle} onChange={(event) => {
                      clearFormalPreview();
                      setSubtitle(event.target.value);
                    }} placeholder="可选" />
                  </label>
                  <label className={styles.answerToggle}>
                    <input type="checkbox" checked={showAnswers} onChange={(event) => {
                      clearFormalPreview();
                      setShowAnswers(event.target.checked);
                    }} />
                    <span>包含答案与解析</span>
                  </label>
                  <Button
                    size="small"
                    leadingVisual={Eye}
                    disabled={!paper.items.length || saveState !== "saved" || previewLoading}
                    onClick={() => void generateFormalPreview()}
                  >
                    {previewLoading ? "正在编译…" : "生成正式预览"}
                  </Button>
                </div>
                <div className={styles.statGrid}>
                  <div className={styles.statCard}><strong>{stats.total}</strong><span>题目总数</span></div>
                  <div className={styles.statCard}><strong>{paper.knowledge_tags.length}</strong><span>知识点范围</span></div>
                  <div className={styles.statCard}><strong>{stats.easy}</strong><span>容易</span></div>
                  <div className={styles.statCard}><strong>{stats.medium}</strong><span>适中</span></div>
                  <div className={styles.statCard}><strong>{stats.hard}</strong><span>困难</span></div>
                </div>
                <details style={{ marginTop: 16 }}>
                  <summary style={{ cursor: "pointer", color: "var(--fgColor-muted)", fontSize: 13 }}><MoreHorizontal size={14} /> 更多操作</summary>
                  <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 2 }}>
                    <Button size="small" onClick={sortByDifficulty}>按难度重新排序</Button>
                    <Button size="small" leadingVisual={Trash2} onClick={() => void saveItems([])}>清空试卷</Button>
                  </Box>
                </details>
              </>
            )}
          </div>
        </aside>
      </div>
    </Box>
  );
}
