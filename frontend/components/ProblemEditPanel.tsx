"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Button, Flash, FormControl, Spinner, Text, TextInput, Textarea } from "@primer/react";
import type { TagDimensionStyle } from "../types/api";
import { overrideProblem } from "../features/tasks";
import { TagPicker } from "./TagPicker";

type OptionDraft = {
  id: string;
  key: string;
  text: string;
};

type ProblemEditPanelProps = {
  taskId: string;
  problem: {
    problem_id: string;
    question_no?: string | null;
    source?: string | null;
    problem_text: string;
    options?: Array<{ key: string; text: string } | null>;
    knowledge_tags?: string[];
    error_tags?: string[];
    user_tags?: string[];
  };
  tagStyles: Record<string, TagDimensionStyle>;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
};

export function ProblemEditPanel({ taskId, problem, tagStyles, onClose, onSaved }: ProblemEditPanelProps) {
  const [questionNo, setQuestionNo] = useState<string>("");
  const [sourceTags, setSourceTags] = useState<string[]>([]);
  const [problemText, setProblemText] = useState<string>("");
  const [options, setOptions] = useState<OptionDraft[]>([]);
  const [optionsError, setOptionsError] = useState<string>("");
  const [knowledgeTags, setKnowledgeTags] = useState<string[]>([]);
  const [errorTags, setErrorTags] = useState<string[]>([]);
  const [userTags, setUserTags] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string>("");

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
    setMessage("");
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
  }, [problem, nextOptionId]);

  const save = useCallback(async () => {
    setIsSaving(true);
    setMessage("");
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

      await overrideProblem(taskId, problem.problem_id, {
        question_no: questionNo.trim() || null,
        source: sourceTags[0]?.trim() || null,
        problem_text: problemText,
        options: parsedOptions,
        knowledge_tags: knowledgeTags,
        error_tags: errorTags,
        user_tags: userTags,
      });
      setMessage("已保存");
      await onSaved();
      onClose();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "保存失败");
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
  ]);

  return (
    <Box sx={{ mb: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2, bg: "canvas.default" }}>
      <Box sx={{ p: 3, borderBottom: "1px solid", borderColor: "border.muted" }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Box>
            <Text sx={{ fontWeight: "bold", display: "block" }}>编辑题目</Text>
            <Text sx={{ color: "fg.muted", fontSize: 1 }}>支持 Markdown/LaTeX，修改后会立即覆盖此题。</Text>
          </Box>
          <Button size="small" onClick={onClose}>关闭</Button>
        </Box>
      </Box>

      <Box sx={{ p: 3, display: "flex", flexDirection: "column", gap: 3 }}>
        {message ? (
          <Flash variant={message === "已保存" ? "success" : "danger"}>
            {message}
          </Flash>
        ) : null}

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
          <Textarea value={problemText} onChange={(e) => setProblemText(e.target.value)} block rows={6} />
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
                  gridTemplateColumns: ["1fr", "80px 1fr 80px"],
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
                <Button size="small" variant="invisible" onClick={() => removeOptionDraft(opt.id)}>
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

        <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
          <Button size="small" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={save} disabled={isSaving}>
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
