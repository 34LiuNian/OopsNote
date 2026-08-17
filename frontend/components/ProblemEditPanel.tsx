"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { Box, Button, Collapse, FormControl, GeometryButton, IconButton, NativeInput, NativeSelect, Spinner, Text, TextInput, Textarea, useReducedMotion } from "@/components/ui/primitives";
import { PlusIcon, TrashIcon } from "@/components/ui/icons";
import { Check, ChevronDown, ChevronRight, CircleStop, Code2, Crop, Eye, History, Image as ImageIcon, ImageMinus, ImagePlus, PanelRight, RefreshCw, Save, Sparkles, Trash2, WandSparkles } from "lucide-react";
import { optionLabel } from "@/lib/content/options";
import { notify } from "@/lib/notify";
import { confirmAction } from "@/lib/confirm";
import { apiErrorCode } from "@/lib/api";
import { useAuthenticatedAssetUrl } from "@/hooks/useAuthenticatedAssetUrl";
import type { DiagramCandidate, DiagramImageTone, DiagramItem, DiagramPlacement, NormalizedRect, TagDimensionStyle } from "../types/api";
import { cancelProblemDiagram, continueProblemDiagram, createProblemDiagramCandidate, deleteProblemDiagramCandidate, overrideProblem, rebuildProblemDiagram, reconstructProblemDiagram, selectProblemDiagramCandidate, updateProblemDiagramSettings } from "../features/tasks";
import { TagPicker } from "./TagPicker";
import { ErrorBanner } from "./ui/ErrorBanner";
import { renderTikz } from "./renderers/TikzRenderer";
import { AuthenticatedSvgMarkup } from "./renderers/AuthenticatedSvgMarkup";
import { FigureCropper, FULL_IMAGE_CROP } from "./image-crop/FigureCropper";
import sxStyles from "./ProblemEditPanel.sx.module.css";

type OptionDraft = {
  id: string;
  text: string;
};

type ProblemEditPanelProps = {
  taskId: string;
  taskAssetPath?: string | null;
  problem: {
    problem_id: string;
    question_no?: string | null;
    chapter?: string | null;
    source?: string | null;
    difficulty_coefficient_override?: number | null;
    section_question_count?: number | null;
    difficulty_needs_review?: boolean;
    problem_text: string;
    diagram_detected?: boolean;
    diagram_enabled?: boolean;
    diagram_kind?: string | null;
    diagram_tikz_source?: string | null;
    diagram_svg?: string | null;
    diagram_image_path?: string | null;
    diagram_image_tone?: DiagramImageTone;
    diagram_placement?: DiagramPlacement;
    diagram_scale_adjustment_percent?: number | null;
    diagram_render_status?: string | null;
    diagram_error?: string | null;
    diagram_error_category?: string | null;
    diagram_needs_review?: boolean;
    diagram_items?: DiagramItem[];
    options?: Array<{ key: string; text: string } | null>;
    knowledge_tags?: string[];
    error_tags?: string[];
    user_tags?: string[];
  };
  tagStyles: Record<string, TagDimensionStyle>;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
};

function CandidatePreview({ candidate }: { candidate: DiagramCandidate }) {
  if (!candidate.svg_path) return <Text className={sxStyles.sx1}>此版本尚未生成预览。</Text>;
  return <AuthenticatedSvgMarkup path={candidate.svg_path} label={`题图版本 ${candidate.ordinal}`} />;
}

const diagramStatusLabel: Record<DiagramItem["status"], string> = {
  detected: "待处理",
  queued: "等待处理",
  generating: "正在生成",
  rendering: "正在编译",
  reviewing: "正在复核",
  ready_tikz: "已就绪",
  ready_image: "已就绪",
  needs_review: "需要复核",
  failed: "处理失败",
  cancelled: "已取消",
};

const diagramPlacementOptions: Array<{ value: string; label: string; placement: DiagramPlacement }> = [
  { value: "side-right", label: "右侧", placement: { kind: "side", side: "right" } },
  { value: "side-left", label: "左侧", placement: { kind: "side", side: "left" } },
  { value: "after-stem", label: "题干与选项之间", placement: { kind: "block", anchor: "after_stem", align: "center" } },
  { value: "after-options", label: "题目下方", placement: { kind: "block", anchor: "after_options", align: "center" } },
  { value: "after-options-right", label: "题目右下", placement: { kind: "block", anchor: "after_options", align: "right" } },
];

function diagramPlacementValue(placement: DiagramPlacement): string {
  if (placement.kind === "side") return `side-${placement.side}`;
  if (placement.anchor === "after_stem") return "after-stem";
  return placement.align === "right" ? "after-options-right" : "after-options";
}

function diagramPlacementLabel(placement: DiagramPlacement): string {
  return diagramPlacementOptions.find((option) => option.value === diagramPlacementValue(placement))?.label ?? "右侧";
}

export function ProblemEditPanel({ taskId, taskAssetPath, problem, tagStyles, onClose, onSaved }: ProblemEditPanelProps) {
  const optionIdRef = useRef(0);
  const nextOptionId = useCallback(() => {
    optionIdRef.current += 1;
    return `opt-${optionIdRef.current}`;
  }, []);

  const [questionNo, setQuestionNo] = useState(() => (problem.question_no || "").toString());
  const [chapter, setChapter] = useState(() => (problem.chapter || "").toString());
  const [sourceTags, setSourceTags] = useState(() => problem.source ? [String(problem.source)] : []);
  const [difficultyCoefficientOverride, setDifficultyCoefficientOverride] = useState(() => (
    typeof problem.difficulty_coefficient_override === "number"
      ? String(problem.difficulty_coefficient_override)
      : ""
  ));
  const [sectionQuestionCount, setSectionQuestionCount] = useState(() => (
    typeof problem.section_question_count === "number" ? String(problem.section_question_count) : ""
  ));
  const [problemText, setProblemText] = useState(() => (problem.problem_text || "").toString());
  const [options, setOptions] = useState<OptionDraft[]>(() => (
    (Array.isArray(problem.options) ? problem.options : []).map((opt, index) => ({
      id: `initial-opt-${index}`,
      text: String(opt?.text || "").trim(),
    }))
  ));
  const [knowledgeTags, setKnowledgeTags] = useState(() => Array.isArray(problem.knowledge_tags) ? problem.knowledge_tags : []);
  const [errorTags, setErrorTags] = useState(() => Array.isArray(problem.error_tags) ? problem.error_tags : []);
  const [userTags, setUserTags] = useState(() => Array.isArray(problem.user_tags) ? problem.user_tags : []);
  const [diagramTikzSource, setDiagramTikzSource] = useState(() => (problem.diagram_tikz_source || "").toString());
  const diagramItem = problem.diagram_items?.[0] ?? null;
  const initialDiagramSourceKind: "tikz" | "image" = problem.diagram_kind === "image"
    || (!problem.diagram_kind && diagramItem?.status === "ready_image")
    || (!problem.diagram_kind && Boolean(diagramItem?.fallback_image_path) && !diagramItem?.candidates.length)
    ? "image"
    : "tikz";
  const initialDiagramEnabled = problem.diagram_enabled
    ?? problem.diagram_detected
    ?? Boolean(problem.diagram_kind);
  const [diagramKind, setDiagramKind] = useState<"none" | "tikz" | "image">(() => (
    initialDiagramEnabled ? initialDiagramSourceKind : "none"
  ));
  const [diagramSourceKind, setDiagramSourceKind] = useState<"tikz" | "image">(initialDiagramSourceKind);
  const [diagramPlacement, setDiagramPlacement] = useState<DiagramPlacement>(() => (
    problem.diagram_placement ?? diagramItem?.placement ?? { kind: "side", side: "right" }
  ));
  const [diagramScaleAdjustmentPercent, setDiagramScaleAdjustmentPercent] = useState(() => (
    typeof problem.diagram_scale_adjustment_percent === "number"
      ? Math.min(200, Math.max(50, Math.round(problem.diagram_scale_adjustment_percent)))
      : 100
  ));
  const [diagramImageCrop, setDiagramImageCrop] = useState<NormalizedRect>(() => diagramItem?.source_region || FULL_IMAGE_CROP);
  const [diagramImageTone, setDiagramImageTone] = useState<DiagramImageTone>(() => problem.diagram_image_tone === "original" ? "original" : "auto");
  const [, setDiagramSvg] = useState<string | null>(() => problem.diagram_svg || null);
  const [, setDiagramRenderStatus] = useState<string | null>(() => problem.diagram_render_status || null);
  const [diagramCompileError, setDiagramCompileError] = useState<string>(() => (problem.diagram_error || "").replace(/\\n/g, "\n"));
  const [diagramCompileErrorCategory, setDiagramCompileErrorCategory] = useState<string>(() => problem.diagram_error_category || "");
  const [isCompilingDiagram, setIsCompilingDiagram] = useState(false);
  const [candidateViewId, setCandidateViewId] = useState(() => diagramItem?.selected_candidate_id || diagramItem?.candidates.at(-1)?.id || null);
  const [diagramInstruction, setDiagramInstruction] = useState("");
  const [diagramMaxCandidates, setDiagramMaxCandidates] = useState("4");
  const [isRunningDiagramAction, setIsRunningDiagramAction] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const reducedMotion = useReducedMotion();
  const [diagramSectionOpen, setDiagramSectionOpen] = useState(() => (
    Boolean(diagramItem) || Boolean(problem.diagram_error) || Boolean(problem.diagram_needs_review)
  ));
  const [tikzView, setTikzView] = useState<"preview" | "source">("preview");
  const [layoutOpen, setLayoutOpen] = useState(false);
  const [diagramAddMenuOpen, setDiagramAddMenuOpen] = useState(false);
  const [isPersistingDiagram, setIsPersistingDiagram] = useState(false);
  const diagramPersistTimerRef = useRef<number | null>(null);

  const effectiveCandidateViewId = diagramItem?.candidates.some((candidate) => candidate.id === candidateViewId)
    ? candidateViewId
    : diagramItem?.selected_candidate_id || diagramItem?.candidates.at(-1)?.id || null;
  const viewedCandidate = diagramItem?.candidates.find((candidate) => candidate.id === effectiveCandidateViewId) ?? null;

  const persistDiagramSettings = useCallback(async (payload: Parameters<typeof updateProblemDiagramSettings>[1]) => {
    if (diagramPersistTimerRef.current !== null) {
      window.clearTimeout(diagramPersistTimerRef.current);
      diagramPersistTimerRef.current = null;
    }
    setIsPersistingDiagram(true);
    try {
      await updateProblemDiagramSettings(taskId, payload);
      await onSaved();
    } catch (error) {
      notify.error({ title: "附图设置保存失败", description: error instanceof Error ? error.message : "请稍后重试" });
      throw error;
    } finally {
      setIsPersistingDiagram(false);
    }
  }, [onSaved, taskId]);

  const scheduleDiagramSettings = useCallback((payload: Parameters<typeof updateProblemDiagramSettings>[1]) => {
    if (diagramPersistTimerRef.current !== null) window.clearTimeout(diagramPersistTimerRef.current);
    diagramPersistTimerRef.current = window.setTimeout(() => {
      diagramPersistTimerRef.current = null;
      void persistDiagramSettings(payload).catch(() => undefined);
    }, 180);
  }, [persistDiagramSettings]);

  const setDiagramMode = useCallback(async (kind: "none" | "tikz" | "image") => {
    if (kind === "none") {
      setDiagramKind("none");
      await persistDiagramSettings({ enabled: false });
      return;
    }
    setDiagramSourceKind(kind);
    setDiagramKind(kind);
    setDiagramSectionOpen(true);
    // A fresh TikZ slot is valid before its first candidate is generated.
    if (kind === "tikz" && !diagramItem?.selected_candidate_id) {
      await persistDiagramSettings({ enabled: true });
      return;
    }
    await persistDiagramSettings({ enabled: true, kind });
  }, [diagramItem?.selected_candidate_id, persistDiagramSettings]);

  const updateDiagramLayout = useCallback(async (patch: { placement?: DiagramPlacement; scale_adjustment_percent?: number }) => {
    if (patch.placement) setDiagramPlacement(patch.placement);
    if (patch.scale_adjustment_percent !== undefined) setDiagramScaleAdjustmentPercent(patch.scale_adjustment_percent);
    await persistDiagramSettings({
      ...patch,
      enabled: diagramKind !== "none",
      kind: diagramSourceKind,
    });
  }, [diagramKind, diagramSourceKind, persistDiagramSettings]);

  const runDiagramAction = useCallback(async (mode: "initial" | "continue" | "rebuild") => {
    const maxCandidates = Number(diagramMaxCandidates);
    if (!Number.isInteger(maxCandidates) || maxCandidates < 1 || maxCandidates > 8) {
      notify.error({ title: "自动候选数须为 1 到 8" });
      return;
    }
    setIsRunningDiagramAction(true);
    try {
      const payload = {
        max_candidates: maxCandidates,
        instruction: diagramInstruction.trim() || null,
        tikz_only: true,
      };
      if (mode === "initial" || !diagramItem) await reconstructProblemDiagram(taskId, payload);
      else if (mode === "continue") await continueProblemDiagram(taskId, diagramItem.id, payload);
      else await rebuildProblemDiagram(taskId, diagramItem.id, payload);
      notify.success({ title: "题图任务已进入队列" });
      await onSaved();
    } catch (error) {
      notify.error({ title: "题图任务提交失败", description: error instanceof Error ? error.message : "请稍后重试" });
    } finally {
      setIsRunningDiagramAction(false);
    }
  }, [diagramInstruction, diagramItem, diagramMaxCandidates, onSaved, taskId]);

  const selectCandidate = useCallback(async (candidate: DiagramCandidate) => {
    if (!diagramItem) return;
    setIsRunningDiagramAction(true);
    try {
      await selectProblemDiagramCandidate(taskId, diagramItem.id, candidate.id);
      setCandidateViewId(candidate.id);
      notify.success({ title: `已选择版本 ${candidate.ordinal}` });
      await onSaved();
    } catch (error) {
      notify.error({ title: "版本切换失败", description: error instanceof Error ? error.message : "请稍后重试" });
    } finally {
      setIsRunningDiagramAction(false);
    }
  }, [diagramItem, onSaved, taskId]);

  const cancelDiagram = useCallback(async () => {
    if (!diagramItem) return;
    setIsRunningDiagramAction(true);
    try {
      await cancelProblemDiagram(taskId, diagramItem.id);
      await onSaved();
    } catch (error) {
      notify.error({ title: "取消题图任务失败", description: error instanceof Error ? error.message : "请稍后重试" });
    } finally {
      setIsRunningDiagramAction(false);
    }
  }, [diagramItem, onSaved, taskId]);

  const addOption = useCallback(() => {
    setOptions((prev) => [...prev, { id: nextOptionId(), text: "" }]);
  }, [nextOptionId]);

  const updateOption = useCallback((id: string, patch: Partial<Omit<OptionDraft, "id">>) => {
    setOptions((prev) => prev.map((opt) => (opt.id === id ? { ...opt, ...patch } : opt)));
  }, []);

  const removeOptionDraft = useCallback((id: string) => {
    setOptions((prev) => prev.filter((opt) => opt.id !== id));
  }, []);

  const compileAndSaveDiagram = useCallback(async () => {
    const source = diagramTikzSource.trim();
    if (!source) {
      setDiagramSvg(null);
      setDiagramRenderStatus("skipped");
      setDiagramCompileError("");
      notify.error({ title: "请先填写 TikZ 源码" });
      return;
    }

    setIsCompilingDiagram(true);
    setDiagramCompileError("");
    setDiagramCompileErrorCategory("");
    try {
      const svg = await renderTikz(source);
      setDiagramSvg(svg);
      setDiagramRenderStatus("ready");
      setDiagramCompileErrorCategory("");
      let itemId = diagramItem?.id;
      if (!itemId) {
        const response = await updateProblemDiagramSettings(taskId, { enabled: true });
        itemId = response.task.problem?.diagram_items?.[0]?.id;
      }
      if (!itemId) throw new Error("无法创建附图项目");
      await createProblemDiagramCandidate(taskId, itemId, source);
      setTikzView("preview");
      notify.success({ title: "已编译并保存 TikZ 版本" });
      await onSaved();
    } catch (err) {
      const message = err instanceof Error ? err.message : "图形编译失败";
      setDiagramSvg(null);
      setDiagramRenderStatus("failed");
      setDiagramCompileError(message.replace(/\\n/g, "\n"));
      const category = apiErrorCode(err) === "renderer_environment_error" ? "human_review" : "";
      setDiagramCompileErrorCategory(category);
      notify.error({ title: category === "human_review" ? "需要人工介入" : "图形编译失败" });
    } finally {
      setIsCompilingDiagram(false);
    }
  }, [diagramItem, diagramTikzSource, onSaved, taskId]);

  const leaveDiagramSource = useCallback(() => {
    setDiagramTikzSource(viewedCandidate?.tikz_source || "");
    setDiagramCompileError("");
    setTikzView("preview");
  }, [viewedCandidate?.tikz_source]);

  const openDiagramSource = useCallback(() => {
    setDiagramTikzSource(viewedCandidate?.tikz_source || diagramTikzSource);
    setDiagramCompileError("");
    setTikzView("source");
  }, [diagramTikzSource, viewedCandidate?.tikz_source]);

  const requestLeaveDiagramSource = useCallback(() => {
    const currentSource = viewedCandidate?.tikz_source || "";
    if (diagramTikzSource !== currentSource) {
      confirmAction({
        title: "放弃未编译的源码？",
        message: "返回预览后，当前未编译的源码修改会丢失。",
        confirmLabel: "放弃修改",
        destructive: true,
        onConfirm: leaveDiagramSource,
      });
      return;
    }
    leaveDiagramSource();
  }, [diagramTikzSource, leaveDiagramSource, viewedCandidate?.tikz_source]);

  const viewCandidateFromSidebar = useCallback((candidate: DiagramCandidate) => {
    const applyView = () => {
      setCandidateViewId(candidate.id);
      setDiagramTikzSource(candidate.tikz_source);
      setDiagramCompileError("");
      setTikzView("preview");
    };
    const currentSource = viewedCandidate?.tikz_source || "";
    if (tikzView === "source" && diagramTikzSource !== currentSource) {
      confirmAction({
        title: "放弃未编译的源码？",
        message: "切换版本会丢弃当前未编译的源码修改。",
        confirmLabel: "放弃修改",
        destructive: true,
        onConfirm: applyView,
      });
      return;
    }
    applyView();
  }, [diagramTikzSource, tikzView, viewedCandidate?.tikz_source]);

  const deleteCandidate = useCallback(async (candidate: DiagramCandidate) => {
    if (!diagramItem) return;
    setIsRunningDiagramAction(true);
    try {
      await deleteProblemDiagramCandidate(taskId, diagramItem.id, candidate.id);
      setCandidateViewId(null);
      notify.success({ title: `已删除版本 ${candidate.ordinal}` });
      await onSaved();
    } catch (error) {
      notify.error({ title: "删除题图版本失败", description: error instanceof Error ? error.message : "请稍后重试" });
    } finally {
      setIsRunningDiagramAction(false);
    }
  }, [diagramItem, onSaved, taskId]);

  const initialDraftSignature = JSON.stringify({
    questionNo: (problem.question_no || "").toString(),
    chapter: (problem.chapter || "").toString(),
    sourceTags: problem.source ? [String(problem.source)] : [],
    difficultyCoefficientOverride: typeof problem.difficulty_coefficient_override === "number"
      ? String(problem.difficulty_coefficient_override)
      : "",
    sectionQuestionCount: typeof problem.section_question_count === "number" ? String(problem.section_question_count) : "",
    problemText: (problem.problem_text || "").toString(),
    options: (Array.isArray(problem.options) ? problem.options : []).map((option) => String(option?.text || "").trim()),
    knowledgeTags: Array.isArray(problem.knowledge_tags) ? problem.knowledge_tags : [],
    errorTags: Array.isArray(problem.error_tags) ? problem.error_tags : [],
    userTags: Array.isArray(problem.user_tags) ? problem.user_tags : [],
  });
  const currentDraftSignature = JSON.stringify({
    questionNo,
    chapter,
    sourceTags,
    difficultyCoefficientOverride,
    sectionQuestionCount,
    problemText,
    options: options.map(({ text }) => text.trim()),
    knowledgeTags,
    errorTags,
    userTags,
  });
  const isDirty = initialDraftSignature !== currentDraftSignature;

  const save = useCallback(async () => {
    setIsSaving(true);

    try {
      const parsedOptions = options.map((option) => option.text.trim()).filter(Boolean);
      const trimmedDifficultyOverride = difficultyCoefficientOverride.trim();
      const parsedDifficultyOverride = trimmedDifficultyOverride === ""
        ? null
        : Number(trimmedDifficultyOverride);
      const trimmedSectionQuestionCount = sectionQuestionCount.trim();
      const parsedSectionQuestionCount = trimmedSectionQuestionCount === ""
        ? null
        : Number(trimmedSectionQuestionCount);
      if (
        trimmedDifficultyOverride !== ""
        && (typeof parsedDifficultyOverride !== "number"
          || !Number.isFinite(parsedDifficultyOverride)
          || parsedDifficultyOverride < 0
          || parsedDifficultyOverride > 1)
      ) {
        notify.error({ title: "难度系数须在 0 到 1 之间" });
        return;
      }
      if (
        trimmedSectionQuestionCount !== ""
        && (parsedSectionQuestionCount === null
          || !Number.isInteger(parsedSectionQuestionCount)
          || parsedSectionQuestionCount < 1)
      ) {
        notify.error({ title: "区段总题数须为正整数" });
        return;
      }

      await overrideProblem(taskId, {
        question_no: questionNo.trim() || null,
        chapter: chapter.trim() || null,
        source: sourceTags[0]?.trim() || null,
        problem_text: problemText,
        options: parsedOptions,
        knowledge_tags: knowledgeTags,
        error_tags: errorTags,
        user_tags: userTags,
        difficulty_coefficient_override: parsedDifficultyOverride,
        section_question_count: parsedSectionQuestionCount,
      });
      notify.success({ title: "已保存" });
      await onSaved();
      onClose();
    } catch (err) {
      notify.error({
        title: "保存失败",
        description: err instanceof Error ? err.message : "请稍后重试",
      });
    } finally {
      setIsSaving(false);
    }
  }, [
    knowledgeTags,
    errorTags,
    onClose,
    onSaved,
    options,
    problemText,
    questionNo,
    chapter,
    sourceTags,
    difficultyCoefficientOverride,
    sectionQuestionCount,
    taskId,
    userTags,
  ]);

  const requestClose = useCallback(() => {
    if (!isDirty && diagramKind === "tikz" && diagramItem && diagramItem.candidates.length === 0) {
      void persistDiagramSettings({ enabled: false })
        .then(() => onClose())
        .catch(() => undefined);
      return;
    }
    if (isDirty && !isSaving) {
      confirmAction({
        title: "放弃未保存的修改",
        message: "关闭后，本次未保存的修改将丢失。",
        confirmLabel: "放弃修改",
        destructive: true,
        onConfirm: onClose,
      });
      return;
    }
    onClose();
  }, [diagramItem, diagramKind, isDirty, isSaving, onClose, persistDiagramSettings]);

  useEffect(() => {
    if (!isDirty || isSaving) return;
    const preventAccidentalLeave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", preventAccidentalLeave);
    return () => window.removeEventListener("beforeunload", preventAccidentalLeave);
  }, [isDirty, isSaving]);

  useEffect(() => {
    if (!isDirty || isSaving) return;
    const saveWithKeyboard = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "s") return;
      event.preventDefault();
      void save();
    };
    window.addEventListener("keydown", saveWithKeyboard);
    return () => window.removeEventListener("keydown", saveWithKeyboard);
  }, [isDirty, isSaving, save]);

  useEffect(() => {
    if (!diagramItem?.active_run_id) return;
    const timer = window.setInterval(() => { void onSaved(); }, 2000);
    return () => window.clearInterval(timer);
  }, [diagramItem?.active_run_id, onSaved]);

  useEffect(() => () => {
    if (diagramPersistTimerRef.current !== null) window.clearTimeout(diagramPersistTimerRef.current);
  }, []);

  const diagramImagePath = problem.diagram_image_path || taskAssetPath || null;
  const diagramCropSourcePath = taskAssetPath || diagramImagePath;
  const diagramImageUrl = useAuthenticatedAssetUrl(diagramCropSourcePath);
  const diagramPreviewUrl = useAuthenticatedAssetUrl(
    diagramSourceKind === "image" ? diagramImagePath : null,
  );

  return (
    <Box className={["oops-card", sxStyles.sx2].filter(Boolean).join(" ")} >
      <Box className={sxStyles.sx3}>
        <Box className={sxStyles.sx4}>
          <Box className={sxStyles.sx5}>
            <Text className={sxStyles.sx6}>编辑题目</Text>
          </Box>
          <Box className={sxStyles.sx7}>
            {isDirty ? <Text className={sxStyles.sx8}>未保存</Text> : null}
            <Button size="small" variant="invisible" onClick={requestClose}>关闭</Button>
          </Box>
        </Box>
      </Box>

      <Box className={sxStyles.sx9}>
        <Box className={sxStyles.sx10}>
          <FormControl>
            <FormControl.Label>题号</FormControl.Label>
            <TextInput value={questionNo} onChange={(e) => setQuestionNo(e.target.value)} block />
          </FormControl>
          <FormControl>
            <FormControl.Label>章节</FormControl.Label>
            <TextInput value={chapter} onChange={(e) => setChapter(e.target.value)} aria-label="章节" block />
          </FormControl>
          <TagPicker
            title="来源"
            dimension="meta"
            value={sourceTags}
            onChange={(next) => setSourceTags(next.slice(0, 1))}
            styles={tagStyles}
            placeholder="输入来源"
          />
          <FormControl>
            <FormControl.Label>难度系数</FormControl.Label>
            <TextInput
              type="number"
              aria-label="难度系数"
              min={0}
              max={1}
              step={0.01}
              value={difficultyCoefficientOverride}
              onChange={(event) => setDifficultyCoefficientOverride(event.target.value)}
              block
            />
          </FormControl>
          <FormControl>
            <FormControl.Label>区段总题数</FormControl.Label>
            <TextInput
              type="number"
              aria-label="区段总题数"
              min={1}
              step={1}
              value={sectionQuestionCount}
              onChange={(event) => setSectionQuestionCount(event.target.value)}
              block
            />
          </FormControl>
          {problem.difficulty_needs_review && (
            <Text className={sxStyles.sx11}>
              请补全题号、来源和区段总题数，或设置难度系数。
            </Text>
          )}
        </Box>

        <Box className={sxStyles.section}>
          <FormControl>
            <FormControl.Label>题干</FormControl.Label>
            <Textarea
              value={problemText}
              onChange={(e) => setProblemText(e.target.value)}
              block
              rows={8}
              className="problem-statement-editor"
            />
          </FormControl>
        </Box>

        <Box className={[sxStyles.section, "option-editor"].join(" ")}>
          <Box className="option-editor__header">
            <Text className={sxStyles.sx12}>选项</Text>
            <Button size="small" variant="invisible" leadingVisual={PlusIcon} onClick={addOption}>添加</Button>
          </Box>
          <Box className="option-editor__list">
            {options.map((opt, index) => (
              <Box key={opt.id} className="option-editor__row">
                <Text className="option-editor__label">{optionLabel(index)}</Text>
                <Textarea
                  value={opt.text}
                  onChange={(e) => updateOption(opt.id, { text: e.target.value })}
                  aria-label={`选项 ${optionLabel(index)}`}
                  placeholder={`选项 ${optionLabel(index)} 内容`}
                  block
                  rows={1}
                  className="option-editor__input"
                />
                <IconButton
                  size="small"
                  variant="invisible"
                  icon={TrashIcon}
                  aria-label={`删除选项 ${optionLabel(index)}`}
                  className="option-editor__remove"
                  onClick={() => removeOptionDraft(opt.id)}
                />
              </Box>
            ))}
          </Box>
        </Box>

        <Box className={sxStyles.sx13}>
          <Text className={sxStyles.sx14}>分类与标签</Text>
          <Box className="problem-tag-grid">
            <TagPicker
              title="知识体系"
              dimension="knowledge"
              value={knowledgeTags}
              onChange={setKnowledgeTags}
              styles={tagStyles}
              placeholder="搜索或添加"
            />
            <TagPicker
              title="错题归因"
              dimension="error"
              value={errorTags}
              onChange={setErrorTags}
              styles={tagStyles}
              placeholder="搜索或添加"
            />
            <TagPicker
              title="自定义"
              dimension="custom"
              value={userTags}
              onChange={setUserTags}
              styles={tagStyles}
              enableRemoteSearch={false}
              placeholder="输入后回车"
            />
          </Box>
        </Box>

        <Box className={[sxStyles.section, sxStyles.diagramSection].join(" ")}>
          {diagramKind === "none" ? (
            <Box className={sxStyles.diagramOffState}>
              <Box className={sxStyles.diagramOffCopy}>
                <Box className={sxStyles.diagramOffTitleRow}>
                  {diagramSourceKind === "tikz" && viewedCandidate ? (
                    <Box className={sxStyles.diagramOffPreview}><CandidatePreview candidate={viewedCandidate} /></Box>
                  ) : diagramPreviewUrl ? (
                    <Image src={diagramPreviewUrl} alt="附图预览" width={72} height={48} unoptimized className={sxStyles.diagramOffPreview} />
                  ) : null}
                  <Box>
                    <Text className={sxStyles.diagramDisclosureTitle}>附图</Text>
                    <Text className={sxStyles.diagramOffSummary}>{diagramItem ? "附图已移除 · 内容已保留" : "尚未添加附图"}</Text>
                  </Box>
                </Box>
              </Box>
              <Box className={sxStyles.diagramAddArea}>
                <Button size="small" variant="primary" leadingVisual={ImagePlus} disabled={isPersistingDiagram} onClick={() => setDiagramAddMenuOpen((open) => !open)}>添加附图</Button>
                {diagramAddMenuOpen ? (
                  <Box className={sxStyles.diagramAddMenu} role="menu">
                    <Button size="small" variant="invisible" leadingVisual={Code2} trailingVisual={ChevronRight} block onClick={() => { setDiagramAddMenuOpen(false); void setDiagramMode("tikz").catch(() => undefined); }}>TikZ · 恢复上次使用的版本</Button>
                    <Button size="small" variant="invisible" leadingVisual={Crop} trailingVisual={ChevronRight} block disabled={!diagramImagePath} onClick={() => { setDiagramAddMenuOpen(false); void setDiagramMode("image").catch(() => undefined); }}>题图 · 恢复已保存的原图裁剪</Button>
                  </Box>
                ) : null}
              </Box>
            </Box>
          ) : (
            <Box as="section" aria-label="附图工作台" className={sxStyles.diagramWorkbench}>
              <Box className={sxStyles.diagramHeader}>
                <Box className={sxStyles.diagramHeaderCopy}>
                  <Box className={sxStyles.diagramHeaderTitleRow}>
                    <Text className={sxStyles.diagramDisclosureTitle}>附图</Text>
                    <Text className={sxStyles.diagramStatusBadge} data-status={diagramItem?.active_run_id ? "attention" : diagramItem?.needs_review ? "danger" : "success"}>
                      <span aria-hidden />{diagramItem?.active_run_id ? "处理中" : diagramItem?.needs_review ? "需复核" : "已就绪"}
                    </Text>
                  </Box>
                  <Text className={sxStyles.diagramHeaderSummary} truncate>
                    {diagramKind === "tikz" ? `TikZ · ${viewedCandidate ? `版本 ${viewedCandidate.ordinal}` : "尚无版本"}` : "题图裁剪 · 已保存"}
                    {diagramItem?.active_run_id ? " · 正在生成候选" : ""}
                  </Text>
                </Box>
                <Box className={sxStyles.diagramHeaderActions}>
                  <Button size="small" variant="invisible" leadingVisual={ImageMinus} disabled={isPersistingDiagram} onClick={() => void setDiagramMode("none").catch(() => undefined)}>移除</Button>
                  <IconButton size="small" variant="invisible" icon={diagramSectionOpen ? ChevronDown : ChevronRight} aria-label={diagramSectionOpen ? "折叠附图设置" : "展开附图设置"} onClick={() => setDiagramSectionOpen((open) => !open)} />
                </Box>
              </Box>

              {!diagramSectionOpen ? (
                <Box as="figure" aria-label="折叠附图预览" className={sxStyles.diagramCollapsedPreview}>
                  {diagramKind === "tikz" && viewedCandidate ? (
                    <CandidatePreview candidate={viewedCandidate} />
                  ) : diagramKind === "image" && diagramPreviewUrl ? (
                    <Image src={diagramPreviewUrl} alt="当前附图预览" width={1200} height={640} unoptimized />
                  ) : (
                    <Box className={sxStyles.diagramCollapsedEmpty}><ImageIcon size={22} aria-hidden /><Text>暂无可用预览</Text></Box>
                  )}
                </Box>
              ) : null}

              <Collapse expanded={diagramSectionOpen} transitionDuration={reducedMotion ? 0 : 180}>
                <Box className={sxStyles.diagramExpanded}>
                  <Box className={sxStyles.diagramTopbar}>
                    <Box className={sxStyles.diagramTypeSwitch} role="group" aria-label="当前显示的附图类型">
                      <GeometryButton type="button" className={[sxStyles.diagramSegment, diagramKind === "tikz" ? sxStyles.diagramSegmentActive : ""].filter(Boolean).join(" ")} aria-pressed={diagramKind === "tikz"} onClick={() => void setDiagramMode("tikz").catch(() => undefined)}>TikZ</GeometryButton>
                      <GeometryButton type="button" className={[sxStyles.diagramSegment, diagramKind === "image" ? sxStyles.diagramSegmentActive : ""].filter(Boolean).join(" ")} aria-pressed={diagramKind === "image"} disabled={!diagramImagePath} onClick={() => void setDiagramMode("image").catch(() => undefined)}>题图</GeometryButton>
                    </Box>
                    <Button size="small" variant="invisible" leadingVisual={PanelRight} trailingVisual={layoutOpen ? ChevronDown : ChevronRight} aria-expanded={layoutOpen} onClick={() => setLayoutOpen((open) => !open)}>{`${diagramPlacementLabel(diagramPlacement)} · ${diagramScaleAdjustmentPercent === 100 ? "自动字号" : `${diagramScaleAdjustmentPercent}%`}`}</Button>
                  </Box>

                  {layoutOpen ? (
                    <Box className={sxStyles.diagramLayoutPanel}>
                      <Box className={sxStyles.diagramLayoutLine}>
                        <Text className={sxStyles.diagramLayoutLabel}>位置</Text>
                        <NativeSelect
                          aria-label="附图位置"
                          className={sxStyles.diagramSelect}
                          value={diagramPlacementValue(diagramPlacement)}
                          onChange={(event) => {
                            const selected = diagramPlacementOptions.find((option) => option.value === event.target.value);
                            if (selected) void updateDiagramLayout({ placement: selected.placement }).catch(() => undefined);
                          }}
                        >
                          {diagramPlacementOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </NativeSelect>
                      </Box>
                      <Box className={sxStyles.diagramLayoutLine}>
                        <Text className={sxStyles.diagramLayoutLabel}>大小</Text>
                        <NativeInput className={sxStyles.diagramRange} aria-label="自动字号基准微调百分比" type="range" min="50" max="200" step="5" value={diagramScaleAdjustmentPercent} onChange={(event) => { const next = Number(event.target.value); setDiagramScaleAdjustmentPercent(next); scheduleDiagramSettings({ enabled: true, kind: diagramSourceKind, scale_adjustment_percent: next }); }} />
                        <Text className={sxStyles.diagramScaleValue}>{diagramScaleAdjustmentPercent === 100 ? "自动" : `${diagramScaleAdjustmentPercent}%`}</Text>
                      </Box>
                    </Box>
                  ) : null}

                  {diagramKind === "tikz" ? (
                    <Box className={sxStyles.diagramTikzPanel}>
                      <Box className={sxStyles.diagramWorkspace}>
                        <Box className={[sxStyles.diagramWorkspaceLayout, diagramItem?.candidates.length ? sxStyles.diagramWorkspaceLayoutWithSidebar : ""].filter(Boolean).join(" ")}>
                          {diagramItem?.candidates.length ? (
                            <Box as="aside" className={sxStyles.diagramVersionSidebar} aria-label="版本记录">
                              <Box className={sxStyles.diagramVersionSidebarHeader}><History size={14} aria-hidden />版本记录 · {diagramItem.candidates.length}</Box>
                              <Box role="group" aria-label="版本历史列表" className={sxStyles.diagramVersionSidebarList}>
                                {[...diagramItem.candidates].reverse().map((candidate) => {
                                  const isCurrent = candidate.id === diagramItem.selected_candidate_id;
                                  const isViewed = candidate.id === effectiveCandidateViewId;
                                  return <GeometryButton key={candidate.id} type="button" className={[sxStyles.diagramSidebarRow, isViewed ? sxStyles.diagramSidebarRowViewed : ""].filter(Boolean).join(" ")} aria-pressed={isViewed} onClick={() => viewCandidateFromSidebar(candidate)}>
                                    <Box className={sxStyles.diagramVersionCopy}>
                                      <Text className={sxStyles.diagramVersionName}>版本 {candidate.ordinal} · {candidate.source_kind === "ai" ? "AI" : "人工"}</Text>
                                      <Text className={[sxStyles.diagramMuted, isCurrent ? sxStyles.diagramCurrentLabel : ""].filter(Boolean).join(" ")}>{isCurrent ? "当前使用" : isViewed ? "正在查看" : candidate.parent_candidate_id ? "基于上一版本" : "候选版本"}</Text>
                                    </Box>
                                  </GeometryButton>;
                                })}
                              </Box>
                            </Box>
                          ) : null}

                          <Box className={sxStyles.diagramWorkspaceMain}>
                            <Box className={sxStyles.diagramWorkspaceHead}>
                              <Box className={sxStyles.diagramVersionTitle}>
                                <Text className={sxStyles.diagramCurrentVersion}>{viewedCandidate ? `版本 ${viewedCandidate.ordinal}` : "尚无 TikZ 版本"}</Text>
                                {viewedCandidate ? <Text className={sxStyles.diagramMuted}>{viewedCandidate.id === diagramItem?.selected_candidate_id ? `${viewedCandidate.source_kind === "ai" ? "AI 生成" : "人工编译"} · 当前使用` : `${viewedCandidate.source_kind === "ai" ? "AI 生成" : "人工编译"} · 正在查看`}</Text> : null}
                              </Box>
                              {tikzView === "preview" ? <Button size="small" variant="invisible" leadingVisual={Code2} onClick={openDiagramSource}>编辑源码</Button> : <Button size="small" variant="invisible" leadingVisual={Eye} onClick={requestLeaveDiagramSource}>返回预览</Button>}
                            </Box>

                            {viewedCandidate ? (
                              <Box as="section" aria-label="版本详细信息" className={sxStyles.diagramCandidateDetails}>
                                <Box className={sxStyles.diagramCandidateDetailsHead}>
                                  <Text className={sxStyles.diagramCandidateDetailsTitle}>版本详细信息</Text>
                                  <Text className={sxStyles.diagramCandidateMeta}>
                                    {[viewedCandidate.provider, viewedCandidate.model].filter(Boolean).join(" · ") || "本地编译"}
                                  </Text>
                                </Box>
                                <Text className={sxStyles.diagramCandidateReason}>
                                  {viewedCandidate.review_reason || (viewedCandidate.parent_candidate_id ? "基于上一版本编译。" : "候选版本。")}
                                </Text>
                                {viewedCandidate.hard_errors.length ? (
                                  <Box className={sxStyles.diagramCandidateIssue} data-kind="error">
                                    <Text>硬错误</Text>
                                    <Text>{viewedCandidate.hard_errors.join("；")}</Text>
                                  </Box>
                                ) : null}
                                {viewedCandidate.soft_differences.length ? (
                                  <Box className={sxStyles.diagramCandidateIssue} data-kind="muted">
                                    <Text>差异</Text>
                                    <Text>{viewedCandidate.soft_differences.join("；")}</Text>
                                  </Box>
                                ) : null}
                              </Box>
                            ) : null}

                        {tikzView === "preview" ? (
                          <Box className={sxStyles.diagramTabPanel}>
                            {viewedCandidate ? (
                              <>
                                <Box as="figure" aria-label="当前版本预览" className={sxStyles.diagramPreviewFrame}><CandidatePreview candidate={viewedCandidate} /></Box>
                                <Box className={sxStyles.diagramPreviewFooter}>
                                  <Text className={sxStyles.diagramMuted}>{diagramItem?.active_run_id ? "正在生成候选" : "已保存"}</Text>
                                  <Box className={sxStyles.diagramActionRow}>
                                    {viewedCandidate.id !== diagramItem?.selected_candidate_id && viewedCandidate.svg_path && viewedCandidate.pdf_path ? <Button size="small" leadingVisual={Check} disabled={isRunningDiagramAction || Boolean(diagramItem?.active_run_id)} onClick={() => void selectCandidate(viewedCandidate)}>采用此版本</Button> : null}
                                    <Button size="small" variant="danger" leadingVisual={Trash2} disabled={isRunningDiagramAction || Boolean(diagramItem?.active_run_id)} onClick={() => void deleteCandidate(viewedCandidate)}>删除版本</Button>
                                  </Box>
                                </Box>
                              </>
                            ) : (
                              <Box className={sxStyles.diagramEmptyTikz}><Box><Box className={sxStyles.diagramEmptyIcon}><WandSparkles size={22} aria-hidden /></Box><Text className={sxStyles.diagramEmptyTitle}>尚无 TikZ 版本</Text><Text className={sxStyles.diagramMuted}>从原始题图生成第一版</Text></Box></Box>
                            )}

                            <Box className={sxStyles.diagramAiSection}>
                              <Text className={sxStyles.diagramAiTitle}><Sparkles size={15} aria-hidden />AI 优化</Text>
                              <Box className={sxStyles.diagramAiCompose}>
                                <FormControl>
                                  <FormControl.Label htmlFor="diagram-instruction">附加指示（可选）</FormControl.Label>
                                  <TextInput id="diagram-instruction" block placeholder="例如：保留横轴刻度与箭头方向" value={diagramInstruction} onChange={(event) => setDiagramInstruction(event.currentTarget.value)} />
                                </FormControl>
                                <FormControl>
                                  <FormControl.Label htmlFor="diagram-rounds">最大轮数</FormControl.Label>
                                  <NativeSelect id="diagram-rounds" className={sxStyles.diagramSelect} aria-label="最大轮数" value={diagramMaxCandidates} onChange={(event) => setDiagramMaxCandidates(event.currentTarget.value)}>
                                    {[1, 2, 3, 4, 5, 6, 7, 8].map((round) => <option key={round} value={round}>{round}</option>)}
                                  </NativeSelect>
                                </FormControl>
                                <Box className={sxStyles.diagramPrimaryAction}>
                                  {!diagramItem?.candidates.length ? <Button size="small" variant="primary" leadingVisual={WandSparkles} disabled={isRunningDiagramAction || !taskAssetPath} onClick={() => void runDiagramAction("initial")}>AI 生成</Button> : <Button size="small" variant="primary" leadingVisual={Sparkles} disabled={isRunningDiagramAction || Boolean(diagramItem.active_run_id)} onClick={() => void runDiagramAction("continue")}>继续优化</Button>}
                                </Box>
                              </Box>
                              <Box className={sxStyles.diagramAiFooter}>
                                {diagramItem ? <Box className={sxStyles.diagramAiStatus}>
                                  <Text className={sxStyles.diagramStatus} data-status={diagramItem.needs_review || diagramItem.status === "failed" ? "danger" : "muted"}>{diagramStatusLabel[diagramItem.status]}</Text>
                                  {diagramItem.active_run_id ? <Button size="small" variant="danger" leadingVisual={CircleStop} disabled={isRunningDiagramAction} onClick={() => void cancelDiagram()}>取消任务</Button> : null}
                                </Box> : <span />}
                                <Button size="small" variant="invisible" leadingVisual={RefreshCw} disabled={isRunningDiagramAction || Boolean(diagramItem?.active_run_id)} onClick={() => void runDiagramAction("rebuild")}>从原图重新重建</Button>
                              </Box>
                            </Box>

                          </Box>
                        ) : (
                          <Box className={sxStyles.diagramSourceView}>
                            <Box className={sxStyles.diagramSourceShell}>
                              <Box className={sxStyles.diagramSourceHead}><Text family="mono">diagram.tikz</Text><Text className={sxStyles.diagramMuted}>{viewedCandidate ? `基于版本 ${viewedCandidate.ordinal}` : "新建 TikZ 版本"}</Text></Box>
                              <Textarea value={diagramTikzSource} onChange={(event) => { setDiagramTikzSource(event.target.value); setDiagramSvg(null); setDiagramRenderStatus("pending"); setDiagramCompileError(""); }} block rows={14} className={sxStyles.diagramSourceEditor} placeholder="编辑 TikZ 源码。编译并保存后才会生成版本。" />
                            </Box>
                            {diagramCompileError ? <Box className={sxStyles.diagramCompileError}><Text className={sxStyles.diagramCompileErrorTitle}>{diagramCompileErrorCategory === "human_review" ? "需要人工介入" : "编译错误"}</Text><Text className={sxStyles.diagramCompileErrorBody}>{diagramCompileError}</Text></Box> : null}
                            <Box className={sxStyles.diagramSourceActions}>
                              <Button size="small" variant="invisible" onClick={requestLeaveDiagramSource}>放弃修改</Button>
                              <Button size="small" variant="primary" leadingVisual={Save} onClick={() => void compileAndSaveDiagram()} disabled={isCompilingDiagram}>{isCompilingDiagram ? <><Spinner size="small" className={sxStyles.sx35} />编译中…</> : "编译并保存"}</Button>
                            </Box>
                          </Box>
                        )}
                      </Box>
                    </Box>
                  </Box>
                </Box>
                  ) : null}

                  {diagramKind === "image" ? (
                    <Box className={sxStyles.diagramImagePanel}>
                      <Box className={sxStyles.diagramWorkspace}>
                        <Box className={sxStyles.diagramWorkspaceHead}>
                          <Box className={sxStyles.diagramVersionTitle}><Text className={sxStyles.diagramCurrentVersion}>题图裁剪</Text><Text className={sxStyles.diagramMuted}>已保存</Text></Box>
                          <Box className={sxStyles.diagramTypeSwitch} role="group" aria-label="题图色调">
                            <GeometryButton type="button" className={[sxStyles.diagramSegment, diagramImageTone === "auto" ? sxStyles.diagramSegmentActive : ""].filter(Boolean).join(" ")} aria-pressed={diagramImageTone === "auto"} onClick={() => { setDiagramImageTone("auto"); void persistDiagramSettings({ enabled: true, kind: "image", image_tone: "auto" }).catch(() => undefined); }}>自动适配</GeometryButton>
                            <GeometryButton type="button" className={[sxStyles.diagramSegment, diagramImageTone === "original" ? sxStyles.diagramSegmentActive : ""].filter(Boolean).join(" ")} aria-pressed={diagramImageTone === "original"} onClick={() => { setDiagramImageTone("original"); void persistDiagramSettings({ enabled: true, kind: "image", image_tone: "original" }).catch(() => undefined); }}>保留原色</GeometryButton>
                          </Box>
                        </Box>
                        {diagramImageUrl ? <FigureCropper imageUrl={diagramImageUrl} value={diagramImageCrop} tone={diagramImageTone} showToneControls={false} onChange={(next) => { setDiagramImageCrop(next); scheduleDiagramSettings({ enabled: true, kind: "image", image_crop: next }); }} onToneChange={(tone) => { setDiagramImageTone(tone); void persistDiagramSettings({ enabled: true, kind: "image", image_tone: tone }).catch(() => undefined); }} /> : <Text className={sxStyles.sx1}>当前题目没有可用的原始图片。</Text>}
                        <Box className={sxStyles.diagramImageFooter}><Text className={sxStyles.diagramMuted}>裁剪自原始题图 · 拖动选区后立即保存</Text><Crop size={15} aria-hidden /></Box>
                      </Box>
                    </Box>
                  ) : null}
                </Box>
              </Collapse>
            </Box>
          )}
        </Box>

        <Box className={sxStyles.sx41}>
          <Button size="small" variant="invisible" onClick={requestClose}>取消</Button>
          <Button variant="primary" leadingVisual={Save} onClick={save} disabled={isSaving || !isDirty}>
            {isSaving ? (
              <>
                <Spinner size="small" className={sxStyles.sx42} />
                保存中…
              </>
            ) : (
              "保存修改"
            )}
          </Button>
        </Box>
      </Box>
    </Box>
  );
}
