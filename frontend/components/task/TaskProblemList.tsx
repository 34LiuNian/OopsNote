"use client";

import { useState } from "react";
import { Box, Button, Heading, IconButton, Label, Text, Tooltip } from "@primer/react";
import { PencilIcon, CopyIcon, TrashIcon, ChevronDownIcon, ChevronUpIcon } from "@primer/octicons-react";
import type { TagDimensionStyle } from "@/types/api";
import { MarkdownRenderer } from "../renderers/MarkdownRenderer";
import { ProblemCard } from "../ProblemCard";
import { ProblemEditPanel } from "../ProblemEditPanel";
import { deleteProblem } from "@/features/tasks";

type TaskProblemListProps = {
  taskId: string;
  taskDifficulty?: string | null;
  problems: Array<{
    problem_id: string;
    question_no?: string | null;
    question_type?: string | null;
    source?: string | null;
    problem_text: string;
    options?: Array<{ key: string; text: string }>;
    knowledge_tags?: string[];
    error_tags?: string[];
    user_tags?: string[];
  }>;
  solutions: Array<{ problem_id: string; answer: string; explanation: string }>;
  tags: Array<{ problem_id: string; knowledge_points: string[] }>;
  editingKey: string;
  onEdit: (problemId: string) => void;
  onCloseEdit: () => void;
  onSaved: () => Promise<void> | void;
  tagStyles: Record<string, TagDimensionStyle>;
  onStatusMessage?: (message: string) => void;
  onError?: (message: string) => void;
};

export function TaskProblemList({
  taskId,
  taskDifficulty,
  problems,
  solutions,
  tags,
  editingKey,
  onEdit,
  onCloseEdit,
  onSaved,
  tagStyles,
  onStatusMessage,
  onError,
}: TaskProblemListProps) {
  const copyMarkdown = async (problemId: string) => {
    try {
      const p = problems.find((x) => x.problem_id === problemId);
      if (!p) throw new Error("题目不存在");
      const tagResult = tags.find((x) => x.problem_id === problemId);
      const s = solutions.find((x) => x.problem_id === problemId);

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
      onStatusMessage?.("已复制 Markdown");
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "复制失败");
    }
  };

  const removeProblem = async (problemId: string) => {
    if (!window.confirm("确认删除这道题？")) return;
    try {
      await deleteProblem(taskId, problemId);
      await onSaved();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "删除失败");
    }
  };

  return (
    <Box sx={{ mt: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
        <Heading as="h3" sx={{ fontSize: 2, m: 0 }}>
          题目与解答
        </Heading>
        {problems.length > 0 && (
          <Box className="oops-badge oops-badge-muted">{problems.length} 题</Box>
        )}
      </Box>

      {problems.length === 0 ? (
        <Box className="oops-empty-state" sx={{ py: 5 }}>
          <Text as="p" sx={{ fontWeight: 600, fontSize: 2 }}>尚未解析出题目</Text>
          <Text as="p" sx={{ fontSize: 1 }}>如果任务仍在处理中，稍等片刻即可看到结果。</Text>
        </Box>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
          {problems.map((problem, idx) => {
            const solution = solutions.find((s) => s.problem_id === problem.problem_id);
            const tag = tags.find((t) => t.problem_id === problem.problem_id);
            const isEditing = editingKey === problem.problem_id;

            // Collect all tags for display
            const knowledgeTags = Array.isArray(problem.knowledge_tags) ? problem.knowledge_tags : [];
            const errorTagsList = Array.isArray(problem.error_tags) ? problem.error_tags : [];
            const userTagsList = Array.isArray(problem.user_tags) ? problem.user_tags : [];
            const aiKnowledge = tag?.knowledge_points || [];
            const allTags = [...knowledgeTags, ...errorTagsList, ...userTagsList, ...aiKnowledge];

            return (
              <ProblemCardItem
                key={problem.problem_id}
                idx={idx}
                problem={problem}
                solution={solution}
                allTags={allTags}
                taskDifficulty={taskDifficulty}
                isEditing={isEditing}
                taskId={taskId}
                tagStyles={tagStyles}
                onEdit={onEdit}
                onCloseEdit={onCloseEdit}
                onSaved={onSaved}
                onCopy={copyMarkdown}
                onRemove={removeProblem}
              />
            );
          })}
        </Box>
      )}
    </Box>
  );
}

/** Individual problem card with collapsible answer */
function ProblemCardItem({
  idx,
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
  onRemove,
}: {
  idx: number;
  problem: TaskProblemListProps["problems"][0];
  solution?: { problem_id: string; answer: string; explanation: string };
  allTags: string[];
  taskDifficulty?: string | null;
  isEditing: boolean;
  taskId: string;
  tagStyles: Record<string, TagDimensionStyle>;
  onEdit: (id: string) => void;
  onCloseEdit: () => void;
  onSaved: () => Promise<void> | void;
  onCopy: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  const [showAnswer, setShowAnswer] = useState(true);

  return (
    <Box
      className="oops-card"
      sx={{
        overflow: "hidden",
        animation: "slideUp 0.3s ease-out",
        animationDelay: `${idx * 0.05}s`,
        animationFillMode: "both",
      }}
    >
      {/* Card header */}
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
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Text sx={{ fontWeight: 600, fontSize: 2 }}>
            {problem.question_no ? `题 ${problem.question_no}` : `题目 ${idx + 1}`}
          </Text>
          {problem.question_type && (
            <Box className="oops-badge oops-badge-accent">{problem.question_type}</Box>
          )}
          {problem.source && (
            <Text sx={{ fontSize: 0, color: "fg.muted" }}>{problem.source}</Text>
          )}
          {taskDifficulty && (
            <Text sx={{ fontSize: 0, color: "fg.muted" }}>难度：{taskDifficulty}</Text>
          )}
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Tooltip text="编辑" direction="s">
            <IconButton icon={PencilIcon} aria-label="编辑" size="small" variant="invisible" onClick={() => onEdit(problem.problem_id)} />
          </Tooltip>
          <Tooltip text="复制 Markdown" direction="s">
            <IconButton icon={CopyIcon} aria-label="复制" size="small" variant="invisible" onClick={() => onCopy(problem.problem_id)} />
          </Tooltip>
          <Tooltip text="删除" direction="s">
            <IconButton icon={TrashIcon} aria-label="删除" size="small" variant="invisible" sx={{ color: "danger.fg" }} onClick={() => onRemove(problem.problem_id)} />
          </Tooltip>
        </Box>
      </Box>

      {/* Edit panel */}
      {isEditing && (
        <ProblemEditPanel
          taskId={taskId}
          problem={problem}
          tagStyles={tagStyles}
          onClose={onCloseEdit}
          onSaved={onSaved}
        />
      )}

      {/* Problem body */}
      <Box sx={{ px: 3, py: 3 }}>
        <ProblemCard
          questionType={null}
          source={null}
          problemText={problem.problem_text || ""}
          options={problem.options}
          itemKeyPrefix={problem.problem_id}
          fontSize={2}
          showMeta={false}
        />
      </Box>

      {/* Tags row */}
      {allTags.length > 0 && (
        <Box sx={{ px: 3, pb: 2, display: "flex", gap: 1, flexWrap: "wrap" }}>
          {allTags.map((t) => (
            <Label key={t} variant="secondary" sx={{ fontSize: "11px" }}>{t}</Label>
          ))}
        </Box>
      )}

      {/* Collapsible answer section */}
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
                <MarkdownRenderer text={solution.answer || ""} />
              </Box>
              <Box>
                <Text sx={{ fontWeight: 600, fontSize: 1, color: "accent.fg", display: "block", mb: 1 }}>解析</Text>
                <MarkdownRenderer text={solution.explanation || ""} />
              </Box>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
