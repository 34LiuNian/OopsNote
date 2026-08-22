"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Download,
  Eye,
  FileText,
  GripVertical,
  PanelLeft,
  Search,
  Settings2,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import {
  Box,
  Button,
  IconButton,
  NativeInput,
  NativeSelect,
  Spinner,
  Text,
  ToggleSwitch,
} from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { ProblemCard } from "@/components/ProblemCard";
import { ProblemListItem } from "@/components/ProblemListItem";
import {
  compilePaperDraft,
  getPaper,
  listPaperCandidates,
  updatePaper,
} from "@/features/papers";
import {
  defaultPointsFor,
  effectiveItemPoints,
  normalizeDefaultPoints,
} from "@/features/papers/defaultPaperStructure";
import { confirmAction } from "@/lib/confirm";
import { notify } from "@/lib/notify";
import type { PaperDraft, PaperDraftItem, ProblemSummary } from "@/types/api";
import styles from "../../paperEditor.module.css";
import sxStyles from "./page.sx.module.css";

const QUESTION_TYPE_ORDER: Record<string, number> = {
  单选题: 0,
  多选题: 1,
  填空题: 2,
  解答题: 3,
};
type Candidate = ProblemSummary & { difficulty_coefficient?: number | null };
type CandidateDifficultyFilter = "" | "easy" | "medium" | "hard" | "pending";

function storedItems(
  items: PaperDraftItem[],
): Array<Omit<PaperDraftItem, "problem">> {
  return items.map(({ problem: _problem, ...item }) => item);
}
function difficultyBucket(
  value?: number | null,
): Exclude<CandidateDifficultyFilter, ""> {
  return value == null
    ? "pending"
    : value <= 0.5
      ? "easy"
      : value <= 0.8
        ? "medium"
        : "hard";
}
function newItemId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID().replaceAll("-", "")
    : `${Date.now()}${Math.random().toString(16).slice(2)}`;
}
function makePaperItem(
  candidate: Candidate,
  existingItems: PaperDraftItem[],
): PaperDraftItem {
  const ordinal = existingItems.filter(
    (item) => item.question_type === (candidate.question_type ?? "解答题"),
  ).length;
  return {
    id: newItemId(),
    task_id: candidate.task_id,
    problem_id: candidate.problem_id,
    question_type: candidate.question_type ?? "解答题",
    difficulty_coefficient: candidate.difficulty_coefficient,
    points: defaultPointsFor(candidate.question_type ?? "解答题", ordinal),
    answer_space: "standard",
    problem: candidate,
  };
}

function estimateQuestionUnits(item: PaperDraftItem): number {
  const problem = item.problem;
  if (!problem) return 5;
  const textUnits = Math.max(1, Math.ceil((problem.problem_text || "").length / 86));
  const optionUnits = problem.options?.length ? Math.ceil(problem.options.length / 2) : 0;
  const diagramUnits = problem.diagram_detected || problem.diagram_svg || problem.diagram_image_path ? 5 : 0;
  const answerUnits = item.question_type === "解答题"
    ? item.answer_space === "large" ? 8 : item.answer_space === "compact" ? 2 : 5
    : 0;
  return 3 + textUnits + optionUnits + diagramUnits + answerUnits;
}

function paginateItems(items: PaperDraftItem[]): PaperDraftItem[][] {
  const pages: PaperDraftItem[][] = [];
  let current: PaperDraftItem[] = [];
  let units = 0;
  items.forEach((item) => {
    const capacity = pages.length === 0 ? 27 : 34;
    const itemUnits = estimateQuestionUnits(item);
    if (current.length && units + itemUnits > capacity) {
      pages.push(current);
      current = [];
      units = 0;
    }
    current.push(item);
    units += itemUnits;
  });
  if (current.length) pages.push(current);
  return pages;
}
function insertByDifficulty(
  items: PaperDraftItem[],
  nextItem: PaperDraftItem,
): PaperDraftItem[] {
  const next = [...items];
  const same = next
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.question_type === nextItem.question_type);
  if (same.length) {
    const before = same.find(
      ({ item }) =>
        (item.difficulty_coefficient ?? 2) >
        (nextItem.difficulty_coefficient ?? 2),
    );
    next.splice(before?.index ?? same[same.length - 1].index + 1, 0, nextItem);
    return next;
  }
  const beforeIndex = next.findIndex(
    (item) =>
      (QUESTION_TYPE_ORDER[item.question_type] ?? 99) >
      (QUESTION_TYPE_ORDER[nextItem.question_type] ?? 99),
  );
  next.splice(beforeIndex < 0 ? next.length : beforeIndex, 0, nextItem);
  return next;
}

export default function PaperEditorPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const router = useRouter();
  const candidateNodes = useRef<Record<string, HTMLDivElement | null>>({});
  const libraryListRef = useRef<HTMLDivElement | null>(null);
  const pageScrollTopRef = useRef<number | null>(null);
  const [paper, setPaper] = useState<PaperDraft | null>(null);
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [showAnswers, setShowAnswers] = useState(false);
  const [diagramScalePercent, setDiagramScalePercent] = useState(60);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [error, setError] = useState("");
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">(
    "saved",
  );
  const [libraryOpen, setLibraryOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [replaceItemId, setReplaceItemId] = useState<string | null>(null);
  const [activeCandidateId, setActiveCandidateId] = useState<string | null>(
    null,
  );
  const [activePaperItemId, setActivePaperItemId] = useState<string | null>(
    null,
  );
  const [candidateQuery, setCandidateQuery] = useState("");
  const [candidateTypeFilter, setCandidateTypeFilter] = useState("");
  const [candidateDifficultyFilter, setCandidateDifficultyFilter] =
    useState<CandidateDifficultyFilter>("");
  const [showCandidateFilters, setShowCandidateFilters] = useState(false);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const clearFormalPreview = () =>
    setPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });

  useEffect(() => {
    let active = true;
    void getPaper(draftId)
      .then((next) => {
        if (active) {
          setPaper({ ...next, items: normalizeDefaultPoints(next.items) });
          setTitle(next.title);
          setCandidateLoading(true);
        }
      })
      .catch(
        (reason) =>
          active &&
          setError(reason instanceof Error ? reason.message : "试卷加载失败"),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [draftId]);
  useEffect(() => {
    if (!paper || title === paper.title) return;
    const timer = window.setTimeout(() => {
      void updatePaper(draftId, { title })
        .then((next) => {
          setPaper((current) =>
            current
              ? { ...current, title: next.title, updated_at: next.updated_at }
              : next,
          );
          setSaveState("saved");
        })
        .catch((reason) => {
          setSaveState("error");
          notify.error({
            title: "试卷标题保存失败",
            description: reason instanceof Error ? reason.message : "保存失败",
          });
        });
    }, 600);
    return () => window.clearTimeout(timer);
  }, [draftId, paper, title]);
  useEffect(() => {
    if (!paper?.subject) return;
    void listPaperCandidates({
      subject: paper.subject,
      knowledgeTags: paper.knowledge_tags,
      knowledgeNodeIds: paper.knowledge_node_ids,
      limit: 500,
    })
      .then(setCandidates)
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "候选题加载失败"),
      )
      .finally(() => setCandidateLoading(false));
  }, [paper?.knowledge_node_ids, paper?.knowledge_tags, paper?.subject]);
  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );
  useEffect(() => {
    const container = libraryListRef.current;
    const node = activeCandidateId
      ? candidateNodes.current[activeCandidateId]
      : null;
    if (!container || !node) return;
    const page = document.querySelector<HTMLElement>(".oops-content-surface");
    const pageTop = page?.scrollTop ?? 0;
    const containerRect = container.getBoundingClientRect();
    const nodeRect = node.getBoundingClientRect();
    const offset =
      nodeRect.top -
      containerRect.top -
      (container.clientHeight - nodeRect.height) / 2;
    container.scrollBy({ top: offset, behavior: "smooth" });
    const frame = window.requestAnimationFrame(() =>
      page?.scrollTo({ top: pageTop, behavior: "auto" }),
    );
    const timer = window.setTimeout(
      () => page?.scrollTo({ top: pageTop, behavior: "auto" }),
      250,
    );
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [activeCandidateId]);
  useEffect(() => {
    if (pageScrollTopRef.current == null) return;
    const page = document.querySelector<HTMLElement>(".oops-content-surface");
    const top = pageScrollTopRef.current;
    const frame = window.requestAnimationFrame(() => {
      page?.scrollTo({ top, behavior: "auto" });
      pageScrollTopRef.current = null;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activePaperItemId]);

  const usedProblemIds = useMemo(
    () => new Set(paper?.items.map((item) => item.problem_id) ?? []),
    [paper?.items],
  );
  const filteredCandidates = useMemo(() => {
    const query = candidateQuery.trim().toLocaleLowerCase();
    return candidates.filter(
      (candidate) =>
        (!candidateTypeFilter ||
          candidate.question_type === candidateTypeFilter) &&
        (!candidateDifficultyFilter ||
          difficultyBucket(candidate.difficulty_coefficient) ===
            candidateDifficultyFilter) &&
        (!query ||
          [
            candidate.problem_text,
            candidate.source,
            candidate.question_type,
            ...(candidate.knowledge_tags ?? []),
          ]
            .filter(Boolean)
            .join(" ")
            .toLocaleLowerCase()
            .includes(query)),
    );
  }, [
    candidates,
    candidateDifficultyFilter,
    candidateQuery,
    candidateTypeFilter,
  ]);
  const allFilteredInPaper =
    filteredCandidates.length > 0 &&
    filteredCandidates.every((candidate) =>
      usedProblemIds.has(candidate.problem_id),
    );
  const questionTypes = useMemo(
    () =>
      Array.from(
        new Set(
          candidates
            .map((candidate) => candidate.question_type)
            .filter((value): value is string => Boolean(value)),
        ),
      ).sort(),
    [candidates],
  );
  const stats = useMemo(() => {
    const items = paper?.items ?? [];
    const points = items.reduce(
      (total, _item, index) => total + (effectiveItemPoints(items, index) ?? 0),
      0,
    );
    return {
      total: items.length,
      points,
      missingPoints: items.filter((_item, index) => effectiveItemPoints(items, index) == null).length,
    };
  }, [paper?.items]);
  const paperPages = useMemo(
    () => paginateItems(paper?.items ?? []),
    [paper?.items],
  );

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
  function toggleCandidateInPaper(candidate: Candidate) {
    if (!paper) return;
    const existing = paper.items.find(
      (item) => item.problem_id === candidate.problem_id,
    );
    if (existing) {
      if (activePaperItemId === existing.id) setActivePaperItemId(null);
      void saveItems(paper.items.filter((item) => item.id !== existing.id));
      return;
    }
    void saveItems(insertByDifficulty(paper.items, makePaperItem(candidate, paper.items)));
  }
  function toggleAllFilteredCandidates() {
    if (!paper || !filteredCandidates.length) return;
    const candidateIds = new Set(
      filteredCandidates.map((candidate) => candidate.problem_id),
    );
    if (allFilteredInPaper) {
      void saveItems(
        paper.items.filter((item) => !candidateIds.has(item.problem_id)),
      );
      return;
    }
    const next = filteredCandidates
      .filter((candidate) => !usedProblemIds.has(candidate.problem_id))
      .reduce(
        (items, candidate) =>
          insertByDifficulty(items, makePaperItem(candidate, items)),
        paper.items,
      );
    void saveItems(next);
  }
  function chooseReplacement(candidate: Candidate) {
    if (!paper || !replaceItemId) return;
    const replacement = {
      ...makePaperItem(candidate, paper.items.filter((item) => item.id !== replaceItemId)),
      id: replaceItemId,
    };
    setReplaceItemId(null);
    void saveItems(
      paper.items.map((item) =>
        item.id === replacement.id ? replacement : item,
      ),
    );
  }
  function moveItem(itemId: string, direction: -1 | 1) {
    if (!paper) return;
    const index = paper.items.findIndex((item) => item.id === itemId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= paper.items.length) return;
    const next = [...paper.items];
    [next[index], next[target]] = [next[target], next[index]];
    void saveItems(next);
  }
  function dropOn(targetId: string) {
    if (!paper || !draggedId || draggedId === targetId) return;
    const sourceIndex = paper.items.findIndex((item) => item.id === draggedId);
    const targetIndex = paper.items.findIndex((item) => item.id === targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    const next = [...paper.items];
    const [moved] = next.splice(sourceIndex, 1);
    next.splice(targetIndex, 0, moved);
    void saveItems(next);
  }
  function updateItem(itemId: string, changes: Partial<PaperDraftItem>) {
    if (paper)
      void saveItems(
        paper.items.map((item) =>
          item.id === itemId ? { ...item, ...changes } : item,
        ),
      );
  }
  function focusPaperItem(itemId: string, problemId: string) {
    pageScrollTopRef.current =
      document.querySelector<HTMLElement>(".oops-content-surface")?.scrollTop ??
      0;
    setActivePaperItemId(itemId);
    setActiveCandidateId(problemId);
    setCandidateQuery("");
    setCandidateTypeFilter("");
    setCandidateDifficultyFilter("");
    setLibraryOpen(true);
  }
  function removeItem(item: PaperDraftItem) {
    if (!paper) return;
    const snapshot = paper.items;
    void saveItems(snapshot.filter((candidate) => candidate.id !== item.id));
    notify.info({
      title: "已移出试卷",
      description: "原题仍保留在题库中。",
      button: { title: "撤销", onClick: () => void saveItems(snapshot) },
    });
  }
  function clearPaper() {
    if (!paper?.items.length) return;
    const snapshot = paper.items;
    confirmAction({
      title: "清空试卷",
      message: "清空当前试卷中的全部题目？题库中的原题不会删除。",
      confirmLabel: "清空试卷",
      destructive: true,
      onConfirm: async () => {
        await saveItems([]);
        notify.info({
          title: "试卷已清空",
          description: "可以立即恢复刚刚移除的题目。",
          button: { title: "撤销", onClick: () => void saveItems(snapshot) },
        });
      },
    });
  }
  async function generateFormalPreview() {
    if (!paper || saveState !== "saved") return;
    clearFormalPreview();
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const pdf = await compilePaperDraft(draftId, {
        subtitle,
        show_answers: showAnswers,
        diagram_scale_percent: diagramScalePercent,
      });
      setPreviewUrl(URL.createObjectURL(pdf));
    } catch (reason) {
      setPreviewError(
        reason instanceof Error ? reason.message : "试卷编译失败",
      );
    } finally {
      setPreviewLoading(false);
    }
  }
  if (loading)
    return (
      <Box className={sxStyles.sx1}>
        <Spinner />
      </Box>
    );
  if (!paper)
    return (
      <Box className={sxStyles.sx2}>
        <ErrorBanner message={error || "试卷不存在"} title="加载试卷失败" />
        <Text className={sxStyles.sx3}>试卷当前不可用。</Text>
      </Box>
    );
  const activeReplacement = replaceItemId
    ? paper.items.find((item) => item.id === replaceItemId)
    : null;
  const previewPages = paperPages.length ? paperPages : [[]];
  return (
    <Box className={styles.editorPage}>
      <ErrorBanner message={error} title="试卷操作失败" />
      <ErrorBanner message={previewError} title="试卷编译失败" />
      <div className={styles.canvasWorkspace} data-library-open={libraryOpen}>
        <aside className={styles.libraryRail} aria-label="题库选题">
          <div className={styles.libraryBody}>
            <div className={styles.libraryTopbar}>
              <IconButton
                icon={ArrowLeft}
                variant="invisible"
                aria-label="返回草稿"
                title="返回草稿"
                onClick={() => router.push("/papers")}
              />
              <IconButton
                icon={Trash2}
                variant="invisible"
                aria-label="清空试卷"
                title="清空试卷"
                disabled={!paper.items.length}
                onClick={clearPaper}
                className={styles.clearPaperAction}
              />
            </div>
            <Button
              className={styles.mobileLibraryClose}
              size="small"
              variant="invisible"
              onClick={() => setLibraryOpen(false)}
            >
              返回卷面
            </Button>
            {activeReplacement ? (
              <div className={styles.replaceNotice}>
                <span>
                  替换第{" "}
                  {paper.items.findIndex(
                    (item) => item.id === activeReplacement.id,
                  ) + 1}{" "}
                  题
                </span>
                <Button
                  size="small"
                  variant="invisible"
                  onClick={() => setReplaceItemId(null)}
                >
                  取消
                </Button>
              </div>
            ) : null}
            <label className={styles.candidateSearchLabel}>
              <span className="oops-visually-hidden">
                搜索题干、来源或知识点
              </span>
              <div className={styles.candidateSearchInput}>
                <Search size={15} aria-hidden="true" />
                <NativeInput
                  value={candidateQuery}
                  onChange={(event) => setCandidateQuery(event.target.value)}
                  placeholder="搜索题干、来源或知识点"
                  aria-label="搜索题库"
                />
              </div>
            </label>
            <div className={styles.libraryTools}>
              <Button
                size="small"
                variant="invisible"
                leadingVisual={SlidersHorizontal}
                aria-expanded={showCandidateFilters}
                onClick={() => setShowCandidateFilters((current) => !current)}
              >
                {showCandidateFilters ? "收起筛选" : "筛选"}
              </Button>
              {!activeReplacement ? (
                <>
                  <Button
                    size="small"
                    variant="invisible"
                    disabled={
                      !filteredCandidates.length || saveState !== "saved"
                    }
                    onClick={toggleAllFilteredCandidates}
                  >
                    {allFilteredInPaper ? "取消全选" : "全选加入"}
                  </Button>
                </>
              ) : null}
            </div>
            {showCandidateFilters ? (
              <div className={styles.candidateFilters}>
                <label>
                  <span>题型</span>
                  <NativeSelect
                    value={candidateTypeFilter}
                    onChange={(event) =>
                      setCandidateTypeFilter(event.target.value as string)
                    }
                  >
                    <option value="">全部题型</option>
                    {questionTypes.map((questionType) => (
                      <option key={questionType} value={questionType}>
                        {questionType}
                      </option>
                    ))}
                  </NativeSelect>
                </label>
                <label>
                  <span>难度</span>
                  <NativeSelect
                    value={candidateDifficultyFilter}
                    onChange={(event) =>
                      setCandidateDifficultyFilter(
                        event.target.value as CandidateDifficultyFilter,
                      )
                    }
                  >
                    <option value="">全部难度</option>
                    <option value="easy">容易</option>
                    <option value="medium">适中</option>
                    <option value="hard">困难</option>
                    <option value="pending">待标难度</option>
                  </NativeSelect>
                </label>
              </div>
            ) : null}
            <div ref={libraryListRef} className={styles.libraryList}>
              {candidateLoading ? (
                <Box className={styles.inlineLoading}>
                  <Spinner size="small" />
                </Box>
              ) : (
                filteredCandidates.map((candidate) => {
                  const isUsed = usedProblemIds.has(candidate.problem_id);
                  return (
                    <div
                      key={candidate.problem_id}
                      ref={(node) => {
                        candidateNodes.current[candidate.problem_id] = node;
                      }}
                      className={styles.libraryItem}
                      data-selected={isUsed ? "true" : undefined}
                      data-linked={
                        activeCandidateId === candidate.problem_id
                          ? "true"
                          : undefined
                      }
                    >
                      <ProblemListItem
                        item={candidate}
                        selected={isUsed}
                        toggleKey={
                          activeReplacement ? undefined : candidate.problem_id
                        }
                        onToggleSelection={() =>
                          toggleCandidateInPaper(candidate)
                        }
                        showMetaPills
                        showAnswerPeek
                        footer={
                          <>
                            {activeReplacement ? (
                              <Button
                                size="small"
                                variant="secondary"
                                onClick={() => chooseReplacement(candidate)}
                              >
                                替换为此题
                              </Button>
                            ) : null}
                          </>
                        }
                      />
                    </div>
                  );
                })
              )}
              {!candidateLoading && !filteredCandidates.length ? (
                <Text className={styles.emptyText}>
                  没有符合当前条件的题目。
                </Text>
              ) : null}
            </div>
          </div>
        </aside>
        <main className={styles.paperDesk} aria-label="实时试卷画布">
          <div className={styles.deskToolbar}>
            <div className={styles.deskStatus}>
              <strong>{stats.total} 题</strong>
              <span>
                {stats.missingPoints
                  ? `${stats.missingPoints} 题待定分值`
                  : `共 ${stats.points} 分`}
              </span>
              <span aria-live="polite">
                {saveState === "saving"
                  ? "正在保存"
                  : saveState === "error"
                    ? "保存失败"
                    : "已保存"}
              </span>
            </div>
            <div className={styles.deskCommands}>
              <Button
                className={styles.mobileLibraryToggle}
                size="small"
                variant="secondary"
                leadingVisual={PanelLeft}
                onClick={() => setLibraryOpen(true)}
              >
                题库
              </Button>
              <Button
                size="small"
                variant="secondary"
                leadingVisual={Settings2}
                onClick={() => setSettingsOpen((current) => !current)}
                aria-expanded={settingsOpen}
              >
                卷面设置
              </Button>
              <Button
                size="small"
                variant="primary"
                leadingVisual={Eye}
                disabled={!paper.items.length || saveState !== "saved"}
                loading={previewLoading}
                onClick={() => void generateFormalPreview()}
              >
                PDF 预览
              </Button>
            </div>
          </div>
          {settingsOpen ? (
            <section className={styles.settingsPopover} aria-label="卷面设置">
              <div className={styles.settingsGrid}>
                <label>
                  <span>题图缩放（%）</span>
                  <NativeInput
                    type="number"
                    min={25}
                    max={200}
                    step={5}
                    value={diagramScalePercent}
                    onChange={(event) => {
                      const value = event.target.valueAsNumber;
                      if (Number.isFinite(value)) {
                        clearFormalPreview();
                        setDiagramScalePercent(
                          Math.min(200, Math.max(25, value)),
                        );
                      }
                    }}
                  />
                </label>
                <label className={styles.answerToggle}>
                  <span>导出答案版</span>
                  <ToggleSwitch
                    checked={showAnswers}
                    onChange={(event) => {
                      clearFormalPreview();
                      setShowAnswers(event.target.checked);
                    }}
                  />
                </label>
              </div>
            </section>
          ) : null}
          {previewUrl ? (
            <section className={styles.previewPanel}>
              <div className={styles.previewHeader}>
                <strong>{showAnswers ? "答案版 PDF" : "学生版 PDF"}</strong>
                <div className={styles.previewActions}>
                  <a
                    className={styles.previewDownload}
                    href={previewUrl}
                    download={`${paper.title || "试卷"}.pdf`}
                  >
                    <Download size={15} /> 下载
                  </a>
                  <Button
                    size="small"
                    variant="invisible"
                    onClick={clearFormalPreview}
                  >
                    返回卷面
                  </Button>
                </div>
              </div>
              <iframe
                title="试卷 PDF 正式预览"
                src={previewUrl}
                className={styles.previewFrame}
              />
            </section>
          ) : (
            <div className={styles.a4Viewport}>
              {previewPages.map((pageItems, pageIndex) => (
                <article className={styles.a4Page} key={`page-${pageIndex}`}>
                  {pageIndex === 0 ? (
                    <header className={styles.a4Header}>
                      <p className={styles.a4Secret}>试卷草稿</p>
                      <label className={styles.a4TitleField}>
                        <span className="oops-visually-hidden">试卷标题</span>
                        <NativeInput
                          value={title}
                          aria-label="试卷标题"
                          className={styles.a4TitleInput}
                          placeholder="未命名试卷"
                          onChange={(event) => {
                            clearFormalPreview();
                            setTitle(event.target.value);
                            setSaveState("saving");
                          }}
                        />
                      </label>
                      <label className={styles.a4SubtitleField}>
                        <span className="oops-visually-hidden">副标题或考试说明</span>
                        <NativeInput
                          value={subtitle}
                          aria-label="副标题或考试说明"
                          className={styles.a4SubtitleInput}
                          placeholder="副标题或考试说明（可选）"
                          onChange={(event) => {
                            clearFormalPreview();
                            setSubtitle(event.target.value);
                          }}
                        />
                      </label>
                      <p className={styles.a4Meta}>
                        本试卷共 {stats.total} 题 · 满分 {stats.points} 分
                      </p>
                    </header>
                  ) : null}
                  {pageItems.length ? (
                    <div className={styles.a4Questions}>
                    {pageItems.map((item, pageItemIndex) => {
                      const index = paper.items.findIndex((candidate) => candidate.id === item.id);
                      const previous = paper.items[index - 1];
                      const showSection = pageItemIndex === 0 || previous?.question_type !== item.question_type;
                      const points = effectiveItemPoints(paper.items, index);
                      return (
                      <div key={item.id} className={styles.a4QuestionGroup}>
                        {showSection ? (
                          <div className={styles.a4SectionHeading}>
                            <span>{item.question_type}</span>
                            <span>{paper.items.filter((candidate) => candidate.question_type === item.question_type).length} 题</span>
                          </div>
                        ) : null}
                      <section
                        className={styles.a4Question}
                        data-active={
                          activePaperItemId === item.id ? "true" : undefined
                        }
                        draggable
                        onDragStart={() => setDraggedId(item.id)}
                        onDragEnd={() => setDraggedId(null)}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={() => dropOn(item.id)}
                        tabIndex={0}
                        onMouseDown={(event) => {
                          if (event.button === 0) {
                            event.preventDefault();
                            event.currentTarget.focus({ preventScroll: true });
                          }
                        }}
                        onClick={() => focusPaperItem(item.id, item.problem_id)}
                        onKeyDown={(event) => {
                          if (event.altKey && event.key === "ArrowUp") {
                            event.preventDefault();
                            moveItem(item.id, -1);
                          }
                          if (event.altKey && event.key === "ArrowDown") {
                            event.preventDefault();
                            moveItem(item.id, 1);
                          }
                        }}
                      >
                        <div className={styles.a4QuestionHead}>
                          <strong>{index + 1}.</strong>
                          <span className={styles.a4QuestionPoints}>{points ?? "—"} 分</span>
                        </div>
                        {item.problem ? (
                          <ProblemCard
                            questionNo={null}
                            questionType={null}
                            source={null}
                            problemText={
                              item.problem.problem_text || "（无题干）"
                            }
                            contentFormat={item.problem.content_format}
                            options={item.problem.options}
                            diagramDetected={item.problem.diagram_detected}
                            diagramKind={item.problem.diagram_kind}
                            diagramTikzSource={item.problem.diagram_tikz_source}
                            diagramSvg={item.problem.diagram_svg}
                            diagramImagePath={item.problem.diagram_image_path}
                            diagramImageTone={item.problem.diagram_image_tone}
                            diagramPlacement={item.problem.diagram_placement}
                            diagramScaleAdjustmentPercent={
                              item.problem.diagram_scale_adjustment_percent
                            }
                            diagramCanvasWidthEm={
                              item.problem.diagram_canvas_width_em
                            }
                            diagramCanvasHeightEm={
                              item.problem.diagram_canvas_height_em
                            }
                            diagramRenderStatus={
                              item.problem.diagram_render_status
                            }
                            diagramError={item.problem.diagram_error}
                            diagramNeedsReview={
                              item.problem.diagram_needs_review
                            }
                            itemKeyPrefix={`paper-${item.problem_id}`}
                            showTitle={false}
                            showMeta={false}
                            fontSize={1}
                          />
                        ) : (
                          <Text>原题已不存在，请在题库中替换或移除。</Text>
                        )}
                        {item.question_type === "解答题" &&
                        item.answer_space !== "compact" ? (
                          <div
                            className={styles.answerSpace}
                            data-size={item.answer_space}
                          />
                        ) : null}
                        {activePaperItemId === item.id ? (
                          <div
                            className={styles.paperItemControls}
                            onClick={(event) => event.stopPropagation()}
                          >
                            <IconButton
                              icon={GripVertical}
                              variant="invisible"
                              aria-label={`拖动第 ${index + 1} 题`}
                              className={styles.canvasDragHandle}
                            />
                            <IconButton
                              icon={ArrowUp}
                              variant="invisible"
                              aria-label={`上移第 ${index + 1} 题`}
                              disabled={index === 0}
                              onClick={() => moveItem(item.id, -1)}
                            />
                            <IconButton
                              icon={ArrowDown}
                              variant="invisible"
                              aria-label={`下移第 ${index + 1} 题`}
                              disabled={index === paper.items.length - 1}
                              onClick={() => moveItem(item.id, 1)}
                            />
                            <label className={styles.canvasPoints}>
                              <span>分值</span>
                              <NativeInput
                                type="number"
                                min={0}
                                value={item.points ?? points ?? ""}
                                aria-label={`第 ${index + 1} 题分值`}
                                onChange={(event) =>
                                  updateItem(item.id, {
                                    points:
                                      event.target.value === ""
                                        ? null
                                        : Math.max(
                                            0,
                                            Number(event.target.value),
                                          ),
                                  })
                                }
                              />
                            </label>
                            {item.question_type === "解答题" ? (
                              <NativeSelect
                                className={styles.canvasSelect}
                                aria-label={`第 ${index + 1} 题答题空间`}
                                value={item.answer_space}
                                onChange={(event) =>
                                  updateItem(item.id, {
                                    answer_space: event.target.value as string,
                                  })
                                }
                              >
                                <option value="compact">紧凑</option>
                                <option value="standard">标准留白</option>
                                <option value="large">宽裕留白</option>
                              </NativeSelect>
                            ) : null}
                            <Button
                              size="small"
                              variant="secondary"
                              onClick={() => {
                                setReplaceItemId(item.id);
                                setActiveCandidateId(null);
                              }}
                            >
                              替换
                            </Button>
                            <IconButton
                              icon={Trash2}
                              variant="invisible"
                              aria-label={`移除第 ${index + 1} 题`}
                              onClick={() => removeItem(item)}
                            />
                          </div>
                        ) : null}
                      </section>
                      </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className={styles.a4Empty}>
                    <FileText size={24} aria-hidden="true" />
                    <p>从左侧题库选择题目，卷面将在这里即时生成。</p>
                  </div>
                )}
                  <footer className={styles.a4PageFooter}>第 {pageIndex + 1} / {previewPages.length} 页</footer>
                </article>
              ))}
            </div>
          )}
        </main>
      </div>
    </Box>
  );
}
