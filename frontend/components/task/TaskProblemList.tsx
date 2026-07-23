"use client";

import { useState } from "react";
import { Box, Heading, IconButton, Label, Text, Tooltip } from "@/components/ui/primitives";
import { PencilIcon, CopyIcon, ChevronDownIcon, ChevronUpIcon } from "@/components/ui/icons";
import type { ContentFormat, TagDimensionStyle } from "@/types/api";
import { MarkdownRenderer } from "../renderers/MarkdownRenderer";
import { ProblemCard } from "../ProblemCard";
import { ProblemEditPanel } from "../ProblemEditPanel";
import { rerenderProblemDiagram } from "@/features/tasks";

type TaskProblem = {
  problem_id: string;
  question_no?: string | null;
  question_type?: string | null;
  source?: string | null;
  diagram_detected?: boolean;
  diagram_kind?: string | null;
  diagram_tikz_source?: string | null;
  diagram_svg?: string | null;
  diagram_render_status?: string | null;
  diagram_error?: string | null;
  diagram_needs_review?: boolean;
  problem_text: string;
  content_format?: ContentFormat;
  options?: Array<{ key: string; text: string }>;
  knowledge_tags?: string[];
  error_tags?: string[];
  user_tags?: string[];
};

type TaskSolution = {
  problem_id: string;
  answer: string;
  explanation: string;
};

type TaskProblemDetailProps = {
  taskId: string;
  taskDifficulty?: string | null;
  problem: TaskProblem | null;
  solution: TaskSolution | null;
  tag: { problem_id: string; knowledge_points: string[] } | null;
  editingKey: string;
  onEdit: (problemId: string) => void;
  onCloseEdit: () => void;
  onSaved: () => Promise<void> | void;
  tagStyles: Record<string, TagDimensionStyle>;
  onStatusMessage?: (message: string) => void;
  onError?: (message: string) => void;
};

export function TaskProblemDetail({
  taskId,
  taskDifficulty,
  problem,
  solution,
  tag,
  editingKey,
  onEdit,
  onCloseEdit,
  onSaved,
  tagStyles,
  onStatusMessage,
  onError,
}: TaskProblemDetailProps) {
  const copyMarkdown = async () => {
    if (!problem) return;
    try {
      const lines: string[] = [];
      lines.push(`# ${problem.question_no ? `题号 ${problem.question_no}` : "题目"}`);
      if (problem.source) lines.push(`来源：${problem.source}`);
      lines.push("", "## 题干", problem.problem_text || "", "");

      if (problem.diagram_detected && problem.diagram_tikz_source) {
        lines.push("## 识别图 (TikZ)", "```tikz", problem.diagram_tikz_source, "```", "");
      }

      const knowledgeTags = Array.isArray(problem.knowledge_tags) ? problem.knowledge_tags : [];
      const errorTags = Array.isArray(problem.error_tags) ? problem.error_tags : [];
      const userTags = Array.isArray(problem.user_tags) ? problem.user_tags : [];
      const aiKnowledge = tag?.knowledge_points || [];

      lines.push("## 标签");
      if (knowledgeTags.length) lines.push(`- 知识体系：${knowledgeTags.join("，")}`);
      if (errorTags.length) lines.push(`- 错题归因：${errorTags.join("，")}`);
      if (userTags.length) lines.push(`- 自定义：${userTags.join("，")}`);
      if (aiKnowledge.length) lines.push(`- AI 知识点：${aiKnowledge.join("，")}`);
      if (!knowledgeTags.length && !errorTags.length && !userTags.length && !aiKnowledge.length) {
        lines.push("- （无）");
      }
      lines.push("");

      if (solution) {
        lines.push("## 答案", solution.answer || "", "", "## 解析", solution.explanation || "", "");
      }

      await navigator.clipboard.writeText(lines.join("\n"));
      onStatusMessage?.("已复制 Markdown");
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "复制失败");
    }
  };

  const retryDiagram = async () => {
    if (!problem) return;
    try {
      onStatusMessage?.("开始重试自动识图...");
      await rerenderProblemDiagram(taskId);
      await onSaved();
      onStatusMessage?.("自动识图重试完成");
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "自动识图重试失败");
    }
  };

  const knowledgeTags = Array.isArray(problem?.knowledge_tags) ? problem.knowledge_tags : [];
  const errorTags = Array.isArray(problem?.error_tags) ? problem.error_tags : [];
  const userTags = Array.isArray(problem?.user_tags) ? problem.user_tags : [];
  const aiKnowledge = tag?.knowledge_points || [];
  const allTags = Array.from(new Set([...knowledgeTags, ...errorTags, ...userTags, ...aiKnowledge]));

  return (
    <Box sx={{ mt: 3 }}>
      <Heading as="h3" sx={{ fontSize: 2, m: 0, mb: 3 }}>
        题目与解答
      </Heading>

      {!problem ? (
        <Box className="oops-empty-state" sx={{ py: 5 }}>
          <Text as="p" sx={{ fontWeight: 600, fontSize: 2 }}>尚未解析出题目</Text>
          <Text as="p" sx={{ fontSize: 1 }}>如果任务仍在处理中，稍等片刻即可看到结果。</Text>
        </Box>
      ) : (
        <ProblemDetailCard
          problem={problem}
          solution={solution}
          allTags={allTags}
          taskDifficulty={taskDifficulty}
          isEditing={editingKey === problem.problem_id}
          taskId={taskId}
          tagStyles={tagStyles}
          onEdit={() => onEdit(problem.problem_id)}
          onCloseEdit={onCloseEdit}
          onSaved={onSaved}
          onCopy={copyMarkdown}
          onRetryDiagram={retryDiagram}
        />
      )}
    </Box>
  );
}

function ProblemDetailCard({
  problem,
  solution,
  allTags,
  taskDifficulty,
  isEditing,
  taskId,
  tagStyles,
  onEdit,
  onCloseEdit,
  onSaved,
  onCopy,
  onRetryDiagram,
}: {
  problem: TaskProblem;
  solution: TaskSolution | null;
  allTags: string[];
  taskDifficulty?: string | null;
  isEditing: boolean;
  taskId: string;
  tagStyles: Record<string, TagDimensionStyle>;
  onEdit: () => void;
  onCloseEdit: () => void;
  onSaved: () => Promise<void> | void;
  onCopy: () => void;
  onRetryDiagram: () => Promise<void>;
}) {
  const [showAnswer, setShowAnswer] = useState(true);
  const [isRetryingDiagram, setIsRetryingDiagram] = useState(false);

  const handleRetryDiagram = async () => {
    if (isRetryingDiagram) return;
    setIsRetryingDiagram(true);
    try {
      await onRetryDiagram();
    } finally {
      setIsRetryingDiagram(false);
    }
  };

  return (
    <Box className="oops-card" sx={{ overflow: "hidden", animation: "slideUp 0.3s ease-out" }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 3,
          py: 2,
          borderBottom: "1px solid",
          borderColor: "border.muted",
          bg: "canvas.subtle",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap", flex: 1, minWidth: 0 }}>
          <Text sx={{ fontWeight: 600, fontSize: 2 }}>
            {problem.question_no ? `题 ${problem.question_no}` : "题目"}
          </Text>
          {problem.question_type && <Box className="oops-badge oops-badge-accent">{problem.question_type}</Box>}
          {problem.source && <Text sx={{ fontSize: 0, color: "fg.muted" }}>{problem.source}</Text>}
          {taskDifficulty && <Text sx={{ fontSize: 0, color: "fg.muted" }}>难度：{taskDifficulty}</Text>}
        </Box>
        <Box sx={{ display: "flex", gap: 1, flexShrink: 0 }}>
          <Tooltip text="编辑" direction="s">
            <IconButton icon={PencilIcon} aria-label="编辑" size="small" variant="invisible" onClick={onEdit} />
          </Tooltip>
          <Tooltip text="复制 Markdown" direction="s">
            <IconButton icon={CopyIcon} aria-label="复制" size="small" variant="invisible" onClick={onCopy} />
          </Tooltip>
        </Box>
      </Box>

      {isEditing && (
        <ProblemEditPanel
          taskId={taskId}
          problem={problem}
          tagStyles={tagStyles}
          onClose={onCloseEdit}
          onSaved={onSaved}
        />
      )}

      <Box sx={{ px: 3, py: 3 }}>
        <ProblemCard
          questionType={null}
          source={null}
          problemText={problem.problem_text || ""}
          contentFormat={problem.content_format}
          options={problem.options}
          diagramDetected={problem.diagram_detected}
          diagramKind={problem.diagram_kind}
          diagramTikzSource={problem.diagram_tikz_source}
          diagramSvg={problem.diagram_svg}
          diagramRenderStatus={problem.diagram_render_status}
          diagramError={problem.diagram_error}
          diagramNeedsReview={problem.diagram_needs_review}
          onRetryDiagram={problem.diagram_render_status === "failed" || problem.diagram_needs_review ? handleRetryDiagram : undefined}
          isRetryingDiagram={isRetryingDiagram}
          itemKeyPrefix={problem.problem_id}
          fontSize={2}
          showMeta={false}
        />
      </Box>

      {allTags.length > 0 && (
        <Box sx={{ px: 3, pb: 2, display: "flex", gap: 1, flexWrap: "wrap" }}>
          {allTags.map((value) => (
            <Label key={value} variant="secondary" sx={{ fontSize: "11px" }}>{value}</Label>
          ))}
        </Box>
      )}

      {solution && (
        <Box sx={{ borderTop: "1px solid", borderColor: "border.muted" }}>
          <Box
            onClick={() => setShowAnswer(!showAnswer)}
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              px: 3,
              py: 2,
              cursor: "pointer",
              bg: "canvas.subtle",
              "&:hover": { bg: "neutral.muted" },
              "&:active": { bg: "neutral.muted" },
              transition: "background-color var(--oops-transition-fast)",
              userSelect: "none",
            }}
          >
            <Text sx={{ fontWeight: 600, fontSize: 1, color: "fg.muted" }}>
              {showAnswer ? "收起答案与解析" : "展开答案与解析"}
            </Text>
            {showAnswer ? <ChevronUpIcon size={16} /> : <ChevronDownIcon size={16} />}
          </Box>
          {showAnswer && (
            <Box sx={{ px: 3, py: 3 }}>
              <Box sx={{ mb: 3 }}>
                <Text sx={{ fontWeight: 600, fontSize: 1, color: "accent.fg", display: "block", mb: 1 }}>答案</Text>
                <MarkdownRenderer text={solution.answer || ""} format={problem.content_format} />
              </Box>
              <Box>
                <Text sx={{ fontWeight: 600, fontSize: 1, color: "accent.fg", display: "block", mb: 1 }}>解析</Text>
                <MarkdownRenderer text={solution.explanation || ""} format={problem.content_format} />
              </Box>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
