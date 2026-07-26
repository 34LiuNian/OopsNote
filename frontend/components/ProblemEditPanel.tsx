"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Button, FormControl, Spinner, Text, TextInput, Textarea } from "@/components/ui/primitives";
import { notify } from "@/lib/notify";
import type { TagDimensionStyle } from "../types/api";
import { overrideProblem } from "../features/tasks";
import { TagPicker } from "./TagPicker";
import { SvgMarkup } from "./renderers/SvgMarkup";
import { renderTikz } from "./renderers/TikzRenderer";

type OptionDraft = {
  id: string;
  key: string;
  text: string;
};

type ProblemEditPanelProps = {
  taskId: string;
  taskAssetPath?: string | null;
  problem: {
    problem_id: string;
    question_no?: string | null;
    source?: string | null;
    problem_text: string;
    diagram_detected?: boolean;
    diagram_kind?: string | null;
    diagram_tikz_source?: string | null;
    diagram_svg?: string | null;
    diagram_image_path?: string | null;
    diagram_position?: "left" | "right";
    diagram_scale_percent?: number | null;
    diagram_render_status?: string | null;
    diagram_error?: string | null;
    diagram_needs_review?: boolean;
    options?: Array<{ key: string; text: string } | null>;
    knowledge_tags?: string[];
    error_tags?: string[];
    user_tags?: string[];
  };
  tagStyles: Record<string, TagDimensionStyle>;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
};

export function ProblemEditPanel({ taskId, taskAssetPath, problem, tagStyles, onClose, onSaved }: ProblemEditPanelProps) {
  const [questionNo, setQuestionNo] = useState<string>("");
  const [sourceTags, setSourceTags] = useState<string[]>([]);
  const [problemText, setProblemText] = useState<string>("");
  const [options, setOptions] = useState<OptionDraft[]>([]);
  const [optionsError, setOptionsError] = useState<string>("");
  const [knowledgeTags, setKnowledgeTags] = useState<string[]>([]);
  const [errorTags, setErrorTags] = useState<string[]>([]);
  const [userTags, setUserTags] = useState<string[]>([]);
  const [diagramTikzSource, setDiagramTikzSource] = useState<string>("");
  const [diagramKind, setDiagramKind] = useState<"none" | "tikz" | "image">("none");
  const [diagramPosition, setDiagramPosition] = useState<"left" | "right">("right");
  const [diagramScalePercent, setDiagramScalePercent] = useState<number | null>(null);
  const [diagramSvg, setDiagramSvg] = useState<string | null>(null);
  const [diagramRenderStatus, setDiagramRenderStatus] = useState<string | null>(null);
  const [diagramCompileError, setDiagramCompileError] = useState<string>("");
  const [isCompilingDiagram, setIsCompilingDiagram] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const optionIdRef = useRef(0);
  const nextOptionId = useCallback(() => {
    optionIdRef.current += 1;
    return `opt-${optionIdRef.current}`;
  }, []);

  const addOption = useCallback(() => {
    setOptions((prev) => [...prev, { id: nextOptionId(), key: "", text: "" }]);
  }, [nextOptionId]);

  const updateOption = useCallback((id: string, patch: Partial<Omit<OptionDraft, "id">>) => {
    setOptions((prev) => prev.map((opt) => (opt.id === id ? { ...opt, ...patch } : opt)));
  }, []);

  const removeOptionDraft = useCallback((id: string) => {
    setOptions((prev) => prev.filter((opt) => opt.id !== id));
  }, []);

  useEffect(() => {
    setOptionsError("");
    setQuestionNo((problem.question_no || "").toString());
    setSourceTags(problem.source ? [String(problem.source)] : []);
    setProblemText((problem.problem_text || "").toString());
    const rawOptions = Array.isArray(problem.options) ? problem.options : [];
    if (rawOptions.length > 0) {
      const normalized = rawOptions.map((opt) => ({
        id: nextOptionId(),
        key: String(opt?.key || "").trim(),
        text: String(opt?.text || "").trim(),
      }));
      setOptions(normalized);
    } else {
      setOptions([]);
    }
    setKnowledgeTags(Array.isArray(problem.knowledge_tags) ? problem.knowledge_tags : []);
    setErrorTags(Array.isArray(problem.error_tags) ? problem.error_tags : []);
    setUserTags(Array.isArray(problem.user_tags) ? problem.user_tags : []);
    setDiagramTikzSource((problem.diagram_tikz_source || "").toString());
    setDiagramKind(
      problem.diagram_kind === "image"
        ? "image"
        : problem.diagram_kind === "tikz" || problem.diagram_tikz_source
          ? "tikz"
          : "none",
    );
    setDiagramPosition(problem.diagram_position === "left" ? "left" : "right");
    setDiagramScalePercent(
      typeof problem.diagram_scale_percent === "number"
        ? Math.min(200, Math.max(50, Math.round(problem.diagram_scale_percent)))
        : null,
    );
    setDiagramSvg(problem.diagram_svg || null);
    setDiagramRenderStatus(problem.diagram_render_status || null);
    setDiagramCompileError((problem.diagram_error || "").replace(/\\n/g, "\n"));
  }, [problem, nextOptionId]);

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
    sourceTags: problem.source ? [String(problem.source)] : [],
    problemText: (problem.problem_text || "").toString(),
    options: (Array.isArray(problem.options) ? problem.options : []).map((option) => ({
      key: String(option?.key || "").trim(),
      text: String(option?.text || "").trim(),
    })),
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
    diagramSvg: problem.diagram_svg || null,
    diagramRenderStatus: problem.diagram_render_status || null,
    diagramCompileError: (problem.diagram_error || "").replace(/\\n/g, "\n"),
  });
  const currentDraftSignature = JSON.stringify({
    questionNo,
    sourceTags,
    problemText,
    options: options.map(({ key, text }) => ({ key: key.trim(), text: text.trim() })),
    knowledgeTags,
    errorTags,
    userTags,
    diagramTikzSource,
    diagramKind,
    diagramPosition,
    diagramScalePercent,
    diagramSvg,
    diagramRenderStatus,
    diagramCompileError,
  });
  const isDirty = initialDraftSignature !== currentDraftSignature;

  const save = useCallback(async () => {
    setIsSaving(true);
    setOptionsError("");

    try {
      const normalized = options.map((opt) => ({
        key: opt.key.trim(),
        text: opt.text.trim(),
      }));
      const nonEmpty = normalized.filter((opt) => opt.key || opt.text);
      const hasInvalid = nonEmpty.some((opt) => !opt.key || !opt.text);
      if (hasInvalid) {
        setOptionsError("选项需要同时填写编号和内容");
        setIsSaving(false);
        return;
      }
      const parsedOptions = nonEmpty.map((opt) => ({
        key: opt.key,
        text: opt.text,
      }));

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
        source: sourceTags[0]?.trim() || null,
        problem_text: problemText,
        options: parsedOptions,
        knowledge_tags: knowledgeTags,
        error_tags: errorTags,
        user_tags: userTags,
        diagram_detected: diagramKind !== "none",
        diagram_kind: diagramKind === "none" ? null : diagramKind,
        diagram_tikz_source: diagramKind === "tikz" ? tikzSource : null,
        diagram_svg: diagramKind === "tikz" ? diagramSvg : null,
        diagram_image_path: diagramKind === "image" ? imagePath : null,
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
    problem.problem_id,
    problemText,
    questionNo,
    sourceTags,
    taskId,
    userTags,
    diagramTikzSource,
    diagramKind,
    diagramPosition,
    diagramScalePercent,
    diagramSvg,
    diagramRenderStatus,
    diagramCompileError,
    problem.diagram_image_path,
    taskAssetPath,
  ]);

  const requestClose = useCallback(() => {
    if (isDirty && !isSaving && !window.confirm("放弃未保存的修改？")) return;
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

  const diagramImagePath = problem.diagram_image_path || taskAssetPath || null;
  const diagramImageUrl = diagramImagePath
    ? diagramImagePath.startsWith("/assets/") ? `/api${diagramImagePath}` : diagramImagePath
    : "";

  return (
    <Box className="oops-card" sx={{ overflow: "hidden", animation: "slideUp 0.25s ease-out" }}>
      <Box sx={{ p: 3, borderBottomWidth: 1, borderBottomStyle: "solid", borderBottomColor: "border.muted", bg: "canvas.subtle" }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
          <Box sx={{ flex: 1, minWidth: 220 }}>
            <Text sx={{ fontWeight: 600, fontSize: 2, display: "block" }}>编辑题目</Text>
            <Text sx={{ color: "fg.muted", fontSize: 1, mt: 1 }}>支持 Markdown / LaTeX，保存后更新题库内容。</Text>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
            <Text sx={{ color: isDirty ? "var(--fgColor-attention)" : "fg.muted", fontSize: 0 }}>
              {isDirty ? "有未保存的修改" : "未修改"}
            </Text>
            <Button size="small" variant="invisible" onClick={requestClose}>关闭</Button>
          </Box>
        </Box>
      </Box>

      <Box sx={{ p: 3, display: "flex", flexDirection: "column", gap: 3 }}>
        <Text sx={{ fontWeight: 600, fontSize: 1 }}>基本内容</Text>
        <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3 }}>
          <FormControl>
            <FormControl.Label>题号</FormControl.Label>
            <TextInput value={questionNo} onChange={(e) => setQuestionNo(e.target.value)} block />
          </FormControl>
          <TagPicker
            title="来源"
            dimension="meta"
            value={sourceTags}
            onChange={(next) => setSourceTags(next.slice(0, 1))}
            styles={tagStyles}
            placeholder="输入来源，回车确认"
          />
        </Box>

        <FormControl>
          <FormControl.Label>题干</FormControl.Label>
          <Textarea value={problemText} onChange={(e) => setProblemText(e.target.value)} block rows={4} sx={{ resize: "vertical" }} />
          <Text sx={{ color: "fg.muted", fontSize: 1, mt: 1, display: "block" }}>
            可直接粘贴 Markdown，数学公式用 $...$ 或 \\(...\\)。
          </Text>
        </FormControl>

        <FormControl>
          <FormControl.Label>选项</FormControl.Label>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {options.length === 0 ? (
              <Text sx={{ color: "fg.muted", fontSize: 1 }}>暂无选项，点击“添加选项”开始编辑。</Text>
            ) : null}
            {options.map((opt) => (
              <Box
                key={opt.id}
                sx={{
                  display: "grid",
                  gridTemplateColumns: ["60px 1fr 50px", "80px 1fr 80px"],
                  gap: 2,
                  alignItems: "start",
                }}
              >
                <TextInput
                  value={opt.key}
                  onChange={(e) => updateOption(opt.id, { key: e.target.value })}
                  placeholder="A"
                  block
                />
                <Textarea
                  value={opt.text}
                  onChange={(e) => updateOption(opt.id, { text: e.target.value })}
                  placeholder="选项内容"
                  block
                  rows={2}
                />
                <Button size="small" variant="danger" onClick={() => removeOptionDraft(opt.id)}>
                  删除
                </Button>
              </Box>
            ))}
            <Box>
              <Button size="small" onClick={addOption}>
                添加选项
              </Button>
            </Box>
          </Box>
          {optionsError ? (
            <Text sx={{ color: "danger.fg", mt: 1, display: "block" }}>{optionsError}</Text>
          ) : null}
        </FormControl>

        <Box sx={{ pt: 3, borderTopWidth: 1, borderTopStyle: "solid", borderTopColor: "border.muted" }}>
          <Text sx={{ fontWeight: 600, fontSize: 1, display: "block", mb: 2 }}>分类与标签</Text>
          <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr 1fr"], gap: 3 }}>
            <TagPicker
              title="知识体系"
              dimension="knowledge"
              value={knowledgeTags}
              onChange={setKnowledgeTags}
              styles={tagStyles}
              placeholder="输入搜索，Tab 补全，Enter 选第一"
            />
            <TagPicker
              title="错题归因"
              dimension="error"
              value={errorTags}
              onChange={setErrorTags}
              styles={tagStyles}
              placeholder="输入搜索，Tab 补全，Enter 选第一"
            />
            <TagPicker
              title="自定义"
              dimension="custom"
              value={userTags}
              onChange={setUserTags}
              styles={tagStyles}
              enableRemoteSearch={false}
              placeholder="输入后回车添加"
            />
          </Box>
        </Box>

        <FormControl sx={{ pt: 3, borderTopWidth: 1, borderTopStyle: "solid", borderTopColor: "border.muted" }}>
          <FormControl.Label>题目图形</FormControl.Label>
          <Box sx={{ mt: 2, display: "flex", gap: 2, flexWrap: "wrap" }}>
            <Button size="small" variant={diagramKind === "none" ? "primary" : "default"} onClick={() => setDiagramKind("none")}>
              无图
            </Button>
            <Button
              size="small"
              variant={diagramKind === "tikz" ? "primary" : "default"}
              onClick={() => setDiagramKind("tikz")}
            >
              TikZJax
            </Button>
            <Button
              size="small"
              variant={diagramKind === "image" ? "primary" : "default"}
              disabled={!diagramImagePath}
              onClick={() => setDiagramKind("image")}
            >
              题图
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
              <Text sx={{ color: "fg.muted", fontSize: 1, display: "block", mb: 2 }}>
                当前使用本题的原始图片；自动识别和裁剪题图将在后续实现。
              </Text>
              {diagramImageUrl ? <img src={diagramImageUrl} alt="题图预览" style={{ display: "block", maxWidth: "100%", maxHeight: 320, objectFit: "contain" }} /> : null}
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
              <SvgMarkup svg={diagramSvg} label="TikZ 预览" />
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
