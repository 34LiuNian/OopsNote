"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { Box, Button, FormControl, IconButton, Spinner, Text, TextInput, Textarea } from "@/components/ui/primitives";
import { PlusIcon, TrashIcon } from "@/components/ui/icons";
import { Check, CircleStop, RefreshCw, Sparkles, WandSparkles } from "lucide-react";
import { optionLabel } from "@/lib/content/options";
import { notify } from "@/lib/notify";
import { confirmAction } from "@/lib/confirm";
import { useAuthenticatedAssetUrl } from "@/hooks/useAuthenticatedAssetUrl";
import type { DiagramCandidate, DiagramImageTone, DiagramItem, NormalizedRect, TagDimensionStyle } from "../types/api";
import { cancelProblemDiagram, continueProblemDiagram, overrideProblem, rebuildProblemDiagram, reconstructProblemDiagram, selectProblemDiagramCandidate } from "../features/tasks";
import { TagPicker } from "./TagPicker";
import { ErrorBanner } from "./ui/ErrorBanner";
import { SvgMarkup } from "./renderers/SvgMarkup";
import { renderTikz } from "./renderers/TikzRenderer";
import { FigureCropper, FULL_IMAGE_CROP } from "./image-crop/FigureCropper";

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
    diagram_kind?: string | null;
    diagram_tikz_source?: string | null;
    diagram_svg?: string | null;
    diagram_image_path?: string | null;
    diagram_image_crop?: NormalizedRect | null;
    diagram_image_tone?: DiagramImageTone;
    diagram_position?: "left" | "right";
    diagram_scale_percent?: number | null;
    diagram_render_status?: string | null;
    diagram_error?: string | null;
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
  const imageUrl = useAuthenticatedAssetUrl(candidate.svg_path || null);
  if (!imageUrl) return <Text sx={{ color: "fg.muted", fontSize: 0 }}>此版本尚未生成预览。</Text>;
  return <Image src={imageUrl} alt={`题图版本 ${candidate.ordinal}`} width={800} height={320} unoptimized style={{ display: "block", width: "100%", height: "auto", maxHeight: 320, objectFit: "contain" }} />;
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
  const [diagramKind, setDiagramKind] = useState<"none" | "tikz" | "image">(() => (
    problem.diagram_kind === "image"
      ? "image"
      : problem.diagram_kind === "tikz" || problem.diagram_tikz_source
        ? "tikz"
        : "none"
  ));
  const [diagramPosition, setDiagramPosition] = useState<"left" | "right">(() => problem.diagram_position === "left" ? "left" : "right");
  const [diagramScalePercent, setDiagramScalePercent] = useState<number | null>(() => (
    typeof problem.diagram_scale_percent === "number"
      ? Math.min(200, Math.max(50, Math.round(problem.diagram_scale_percent)))
      : null
  ));
  const [diagramImageCrop, setDiagramImageCrop] = useState<NormalizedRect>(() => problem.diagram_image_crop || FULL_IMAGE_CROP);
  const [diagramImageTone, setDiagramImageTone] = useState<DiagramImageTone>(() => problem.diagram_image_tone === "original" ? "original" : "auto");
  const [diagramSvg, setDiagramSvg] = useState<string | null>(() => problem.diagram_svg || null);
  const [diagramRenderStatus, setDiagramRenderStatus] = useState<string | null>(() => problem.diagram_render_status || null);
  const [diagramCompileError, setDiagramCompileError] = useState<string>(() => (problem.diagram_error || "").replace(/\\n/g, "\n"));
  const [isCompilingDiagram, setIsCompilingDiagram] = useState(false);
  const diagramItem = problem.diagram_items?.[0] ?? null;
  const [candidateViewId, setCandidateViewId] = useState(() => diagramItem?.selected_candidate_id || diagramItem?.candidates.at(-1)?.id || null);
  const [diagramInstruction, setDiagramInstruction] = useState("");
  const [diagramMaxCandidates, setDiagramMaxCandidates] = useState("4");
  const [isRunningDiagramAction, setIsRunningDiagramAction] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const effectiveCandidateViewId = diagramItem?.candidates.some((candidate) => candidate.id === candidateViewId)
    ? candidateViewId
    : diagramItem?.selected_candidate_id || diagramItem?.candidates.at(-1)?.id || null;
  const viewedCandidate = diagramItem?.candidates.find((candidate) => candidate.id === effectiveCandidateViewId) ?? null;

  const runDiagramAction = useCallback(async (mode: "initial" | "continue" | "rebuild") => {
    const maxCandidates = Number(diagramMaxCandidates);
    if (!Number.isInteger(maxCandidates) || maxCandidates < 1 || maxCandidates > 8) {
      notify.error({ title: "自动候选数须为 1 到 8" });
      return;
    }
    setIsRunningDiagramAction(true);
    try {
      const payload = { max_candidates: maxCandidates, instruction: diagramInstruction.trim() || null };
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

  const compileDiagram = useCallback(async () => {
    const source = diagramTikzSource.trim();
    if (!source) {
      setDiagramSvg(null);
      setDiagramRenderStatus("skipped");
      setDiagramCompileError("");
      return;
    }

    setIsCompilingDiagram(true);
    setDiagramCompileError("");
    try {
      const svg = await renderTikz(source);
      setDiagramSvg(svg);
      setDiagramRenderStatus("ready");
      notify.success({ title: "图形编译成功" });
    } catch (err) {
      const message = err instanceof Error ? err.message : "图形编译失败";
      setDiagramSvg(null);
      setDiagramRenderStatus("failed");
      setDiagramCompileError(message.replace(/\\n/g, "\n"));
      notify.error({ title: "图形编译失败" });
    } finally {
      setIsCompilingDiagram(false);
    }
  }, [diagramTikzSource]);

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
    diagramTikzSource: (problem.diagram_tikz_source || "").toString(),
    diagramKind: problem.diagram_kind === "image"
      ? "image"
      : problem.diagram_kind === "tikz" || problem.diagram_tikz_source
        ? "tikz"
        : "none",
    diagramPosition: problem.diagram_position === "left" ? "left" : "right",
    diagramScalePercent: typeof problem.diagram_scale_percent === "number"
      ? Math.min(200, Math.max(50, Math.round(problem.diagram_scale_percent)))
      : null,
    diagramImageCrop: problem.diagram_image_crop || FULL_IMAGE_CROP,
    diagramImageTone: problem.diagram_image_tone === "original" ? "original" : "auto",
    diagramSvg: problem.diagram_svg || null,
    diagramRenderStatus: problem.diagram_render_status || null,
    diagramCompileError: (problem.diagram_error || "").replace(/\\n/g, "\n"),
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
    diagramTikzSource,
    diagramKind,
    diagramPosition,
    diagramScalePercent,
    diagramImageCrop,
    diagramImageTone,
    diagramSvg,
    diagramRenderStatus,
    diagramCompileError,
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

      const tikzSource = diagramTikzSource.trim();
      const imagePath = problem.diagram_image_path || taskAssetPath || null;
      if (diagramKind === "tikz" && !tikzSource) {
        notify.error({ title: "请先填写 TikZ 源码" });
        return;
      }
      if (diagramKind === "image" && !imagePath) {
        notify.error({ title: "当前题目没有可用的原始图片" });
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
        diagram_detected: diagramKind !== "none",
        diagram_kind: diagramKind === "none" ? null : diagramKind,
        diagram_tikz_source: diagramKind === "tikz" ? tikzSource : null,
        diagram_svg: diagramKind === "tikz" ? diagramSvg : null,
        diagram_image_path: diagramKind === "image" ? imagePath : null,
        diagram_image_crop: diagramKind === "image" ? diagramImageCrop : null,
        diagram_image_tone: diagramKind === "image" ? diagramImageTone : undefined,
        diagram_position: diagramPosition,
        diagram_scale_percent: diagramScalePercent,
        diagram_render_status: diagramKind === "image" ? "ready" : diagramKind === "tikz" ? diagramRenderStatus : null,
        diagram_error: diagramKind === "tikz" ? diagramCompileError || null : null,
        diagram_needs_review: diagramKind === "tikz" && diagramRenderStatus === "failed",
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
    diagramTikzSource,
    diagramKind,
    diagramPosition,
    diagramScalePercent,
    diagramImageCrop,
    diagramImageTone,
    diagramSvg,
    diagramRenderStatus,
    diagramCompileError,
    problem.diagram_image_path,
    taskAssetPath,
  ]);

  const requestClose = useCallback(() => {
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
  }, [isDirty, isSaving, onClose]);

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

  const diagramImagePath = problem.diagram_image_path || taskAssetPath || null;
  const diagramCropSourcePath = taskAssetPath || diagramImagePath;
  const diagramImageUrl = useAuthenticatedAssetUrl(diagramCropSourcePath);

  return (
    <Box className="oops-card" sx={{ overflow: "hidden", animation: "slideUp 0.25s ease-out" }}>
      <Box sx={{ px: 3, py: 2, borderBottomWidth: 1, borderBottomStyle: "solid", borderBottomColor: "border.muted", bg: "canvas.subtle" }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
          <Box sx={{ flex: 1, minWidth: 220 }}>
            <Text sx={{ fontWeight: 600, fontSize: 2, display: "block" }}>编辑题目</Text>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
            {isDirty ? <Text sx={{ color: "var(--fgColor-attention)", fontSize: 0 }}>未保存</Text> : null}
            <Button size="small" variant="invisible" onClick={requestClose}>关闭</Button>
          </Box>
        </Box>
      </Box>

      <Box sx={{ p: 3, display: "flex", flexDirection: "column", gap: 3 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr 1fr"], gap: 3 }}>
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
            <Text sx={{ color: "var(--color-text-subtle)", fontSize: "0.8125rem" }}>
              请补全题号、来源和区段总题数，或设置难度系数。
            </Text>
          )}
        </Box>

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

        <Box className="option-editor">
          <Box className="option-editor__header">
            <Text sx={{ fontWeight: 600, fontSize: 1 }}>选项</Text>
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

        <Box sx={{ pt: 3, borderTopWidth: 1, borderTopStyle: "solid", borderTopColor: "border.muted" }}>
          <Text sx={{ fontWeight: 600, fontSize: 1, display: "block", mb: 2 }}>分类与标签</Text>
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

        <FormControl sx={{ pt: 3, borderTopWidth: 1, borderTopStyle: "solid", borderTopColor: "border.muted" }}>
          <FormControl.Label>附图</FormControl.Label>
          <Box sx={{ mt: 2, display: "grid", gridTemplateColumns: ["1fr", "minmax(0, 1fr) 96px"], gap: 2 }}>
            <TextInput
              block
              aria-label="题图优化指示"
              placeholder="本轮附加指示（可选）"
              value={diagramInstruction}
              onChange={(event) => setDiagramInstruction(event.currentTarget.value)}
            />
            <TextInput
              block
              type="number"
              min={1}
              max={8}
              aria-label="自动候选上限"
              value={diagramMaxCandidates}
              onChange={(event) => setDiagramMaxCandidates(event.currentTarget.value)}
            />
          </Box>
          <Box sx={{ mt: 2, display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
            {!diagramItem ? (
              <Button
                size="small"
                leadingVisual={WandSparkles}
                disabled={isRunningDiagramAction || !taskAssetPath}
                onClick={() => void runDiagramAction("initial")}
              >AI 重建</Button>
            ) : (
              <>
                <Button
                  size="small"
                  leadingVisual={Sparkles}
                  disabled={isRunningDiagramAction || Boolean(diagramItem.active_run_id)}
                  onClick={() => void runDiagramAction("continue")}
                >继续优化</Button>
                <Button
                  size="small"
                  variant="default"
                  leadingVisual={RefreshCw}
                  disabled={isRunningDiagramAction || Boolean(diagramItem.active_run_id)}
                  onClick={() => void runDiagramAction("rebuild")}
                >重新重建</Button>
                <Text sx={{ color: diagramItem.needs_review ? "danger.fg" : "fg.muted", fontSize: 0 }}>
                  {diagramItem.status}{diagramItem.active_run_id ? " · 处理中" : ""}
                </Text>
                {diagramItem.active_run_id ? (
                  <Button size="small" variant="danger" leadingVisual={CircleStop} disabled={isRunningDiagramAction} onClick={() => void cancelDiagram()}>
                    取消任务
                  </Button>
                ) : null}
              </>
            )}
          </Box>

          {diagramItem?.candidates.length ? (
            <Box sx={{ mt: 3, display: "grid", gridTemplateColumns: ["1fr", "180px minmax(0, 1fr)"], gap: 3 }}>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {diagramItem.candidates.map((candidate) => (
                  <Button
                    key={candidate.id}
                    size="small"
                    variant={candidate.id === effectiveCandidateViewId ? "primary" : "default"}
                    leadingVisual={candidate.id === diagramItem.selected_candidate_id ? Check : undefined}
                    onClick={() => {
                      setCandidateViewId(candidate.id);
                    }}
                  >版本 {candidate.ordinal} · {candidate.source_kind === "ai" ? "AI" : "人工"}</Button>
                ))}
              </Box>
              {viewedCandidate ? (
                <Box sx={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
                  <Box sx={{ p: 2, border: "1px solid", borderColor: "border.default", borderRadius: 1, bg: "canvas.subtle" }}>
                    <CandidatePreview candidate={viewedCandidate} />
                  </Box>
                  <Text sx={{ color: "fg.muted", fontSize: 0 }}>
                    {viewedCandidate.model || "人工版本"} · {viewedCandidate.decision || "待判断"}
                    {viewedCandidate.parent_candidate_id ? " · 基于上一版本" : ""}
                  </Text>
                  <Textarea
                    readOnly
                    block
                    rows={5}
                    aria-label={`题图版本 ${viewedCandidate.ordinal} 源码`}
                    value={viewedCandidate.tikz_source}
                    sx={{ fontFamily: "mono", fontSize: 0, resize: "vertical" }}
                  />
                  {viewedCandidate.hard_errors.length ? (
                    <>
                      <ErrorBanner message={viewedCandidate.hard_errors.join("；")} title="题图候选存在硬错误" />
                      <Text sx={{ color: "danger.fg", fontSize: 0 }}>硬错误：{viewedCandidate.hard_errors.join("；")}</Text>
                    </>
                  ) : null}
                  {viewedCandidate.soft_differences.length ? (
                    <Text sx={{ color: "fg.muted", fontSize: 0 }}>已接受软差异：{viewedCandidate.soft_differences.join("；")}</Text>
                  ) : null}
                  {viewedCandidate.id !== diagramItem.selected_candidate_id && viewedCandidate.svg_path && viewedCandidate.pdf_path ? (
                    <Button
                      size="small"
                      leadingVisual={Check}
                      disabled={isRunningDiagramAction || Boolean(diagramItem.active_run_id)}
                      onClick={() => void selectCandidate(viewedCandidate)}
                    >采用此版本</Button>
                  ) : null}
                </Box>
              ) : null}
            </Box>
          ) : null}
          <Box sx={{ mt: 2, display: "flex", gap: 2, flexWrap: "wrap" }}>
            <Button size="small" variant={diagramKind === "none" ? "primary" : "default"} onClick={() => setDiagramKind("none")}>
              无附图
            </Button>
            <Button
              size="small"
              variant={diagramKind === "tikz" ? "primary" : "default"}
              onClick={() => setDiagramKind("tikz")}
            >
              TikZ 附图
            </Button>
            <Button
              size="small"
              variant={diagramKind === "image" ? "primary" : "default"}
              disabled={!diagramImagePath}
              onClick={() => setDiagramKind("image")}
            >
              图片附图
            </Button>
          </Box>

          {diagramKind !== "none" ? (
            <Box sx={{ mt: 3, display: "flex", flexDirection: "column", gap: 2 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                <Text sx={{ color: "fg.muted", fontSize: 1 }}>位置</Text>
                <Button size="small" variant={diagramPosition === "right" ? "primary" : "default"} onClick={() => setDiagramPosition("right")}>右侧</Button>
                <Button size="small" variant={diagramPosition === "left" ? "primary" : "default"} onClick={() => setDiagramPosition("left")}>左侧</Button>
              </Box>
              <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                <Text sx={{ color: "fg.muted", fontSize: 1 }}>大小</Text>
                <Button size="small" variant={diagramScalePercent == null ? "primary" : "default"} onClick={() => setDiagramScalePercent(null)}>
                  自适应（与题干等高）
                </Button>
                <Button size="small" variant={diagramScalePercent != null ? "primary" : "default"} onClick={() => setDiagramScalePercent(diagramScalePercent ?? 100)}>
                  自定义
                </Button>
                {diagramScalePercent != null ? (
                  <>
                    <input
                      aria-label="图形大小百分比"
                      type="range"
                      min="50"
                      max="200"
                      step="5"
                      value={diagramScalePercent}
                      onChange={(event) => setDiagramScalePercent(Number(event.target.value))}
                    />
                    <Text sx={{ minWidth: 42, fontSize: 1 }}>{diagramScalePercent}%</Text>
                  </>
                ) : null}
              </Box>
            </Box>
          ) : null}

          {diagramKind === "tikz" ? (
            <>
              <Textarea
                value={diagramTikzSource}
                onChange={(e) => {
                  setDiagramTikzSource(e.target.value);
                  setDiagramSvg(null);
                  setDiagramRenderStatus(e.target.value.trim() ? "pending" : "skipped");
                  setDiagramCompileError("");
                }}
                block
                rows={10}
                sx={{ mt: 3, resize: "vertical", fontFamily: "mono", fontSize: 1 }}
                placeholder="粘贴或编辑 TikZ 源码..."
              />
              <Box sx={{ mt: 2, display: "flex", gap: 2, flexWrap: "wrap" }}>
                <Button size="small" onClick={compileDiagram} disabled={isCompilingDiagram}>
                  {isCompilingDiagram ? (
                    <><Spinner size="small" sx={{ mr: 1 }} />编译中...</>
                  ) : "重编译预览"}
                </Button>
                <Button
                  size="small"
                  variant="invisible"
                  onClick={() => {
                    setDiagramTikzSource("");
                    setDiagramSvg(null);
                    setDiagramRenderStatus("skipped");
                    setDiagramCompileError("");
                  }}
                >
                  清空源码
                </Button>
              </Box>
            </>
          ) : null}

          {diagramKind === "image" ? (
            <Box sx={{ mt: 3 }}>
              {diagramImageUrl ? (
                <FigureCropper
                  imageUrl={diagramImageUrl}
                  value={diagramImageCrop}
                  tone={diagramImageTone}
                  onChange={setDiagramImageCrop}
                  onToneChange={setDiagramImageTone}
                />
              ) : null}
            </Box>
          ) : null}

          {diagramKind === "tikz" && diagramSvg ? (
            <Box
              sx={{
                mt: 2,
                p: 2,
                border: "1px solid",
                borderColor: "border.default",
                borderRadius: 1,
                bg: "canvas.subtle",
                "& svg": { maxWidth: "100%", height: "auto" },
              }}
            >
              <SvgMarkup svg={diagramSvg} label="TikZ 预览" colorMode="themed" />
            </Box>
          ) : null}

          {diagramKind === "tikz" && diagramCompileError ? (
            <Box sx={{ mt: 2, p: 2, border: "1px solid", borderColor: "danger.emphasis", borderRadius: 1, bg: "danger.subtle" }}>
              <Text sx={{ color: "danger.fg", fontSize: 1, fontWeight: 600 }}>编译错误</Text>
              <Text sx={{ display: "block", mt: 1, color: "fg.default", fontSize: 0, whiteSpace: "pre-wrap" }}>
                {diagramCompileError}
              </Text>
            </Box>
          ) : null}
        </FormControl>

        <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end", pt: 2, borderTopWidth: 1, borderTopStyle: "solid", borderTopColor: "border.muted", position: "sticky", bottom: 0, bg: "canvas.default", pb: 2, zIndex: 10 }}>
          <Button size="small" variant="invisible" onClick={requestClose}>取消</Button>
          <Button variant="primary" onClick={save} disabled={isSaving || !isDirty}>
            {isSaving ? (
              <>
                <Spinner size="small" sx={{ mr: 1 }} />
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
