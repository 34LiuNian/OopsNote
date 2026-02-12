"use client";

import { Box, Button, Heading, Label, Text } from "@primer/react";
import type { TagDimensionStyle } from "../../types/api";
import { MarkdownRenderer } from "../MarkdownRenderer";
import { ProblemCard } from "../ProblemCard";
import { ProblemEditPanel } from "../ProblemEditPanel";
import { deleteProblem } from "../../features/tasks";

type TaskProblemListProps = {
  taskId: string;
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
    <Box sx={{ mt: 4 }}>
      <Heading as="h3" sx={{ fontSize: 2, mb: 2, borderBottom: "1px solid", borderColor: "border.muted", pb: 1 }}>
        题目与解答
      </Heading>
      {problems.length === 0 ? (
        <Box sx={{ textAlign: "center", p: 4, color: "fg.muted" }}>
          <Text as="p" sx={{ fontWeight: "bold" }}>尚未解析出题目。</Text>
          <Text as="p" sx={{ fontSize: 1 }}>如果任务仍在处理中，稍等片刻或刷新状态。</Text>
        </Box>
      ) : (
        <Box as="ul" sx={{ listStyle: "none", p: 0, m: 0, display: "flex", flexDirection: "column", gap: 3 }}>
          {problems.map((problem, idx) => {
            const solution = solutions.find((s) => s.problem_id === problem.problem_id);
            const tag = tags.find((t) => t.problem_id === problem.problem_id);

            return (
              <Box as="li" key={problem.problem_id} sx={{ p: 3, bg: "canvas.subtle", borderRadius: 2 }}>
                <Text sx={{ fontWeight: "bold", display: "block", mb: 2, fontSize: 2 }}>
                  {problem.question_no ? `题号 ${problem.question_no}` : `题目 ${idx + 1}`}
                </Text>

                <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 2 }}>
                  <Button size="small" onClick={() => onEdit(problem.problem_id)}>
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
                  <ProblemEditPanel
                    taskId={taskId}
                    problem={problem}
                    tagStyles={tagStyles}
                    onClose={onCloseEdit}
                    onSaved={onSaved}
                  />
                ) : null}

                <Box sx={{ mb: 3 }}>
                  <ProblemCard
                    questionType={problem.question_type}
                    source={problem.source}
                    problemText={problem.problem_text || ""}
                    options={problem.options}
                    itemKeyPrefix={problem.problem_id}
                    fontSize={2}
                  />
                </Box>

                {solution && (
                  <Box sx={{ mb: 2 }}>
                    <Text sx={{ fontWeight: "bold", display: "block" }}>答案：</Text>
                    <MarkdownRenderer text={solution.answer || ""} />
                    <Text sx={{ fontWeight: "bold", display: "block" }}>解析：</Text>
                    <MarkdownRenderer text={solution.explanation || ""} />
                  </Box>
                )}

                {tag && (
                  <Box sx={{ mt: 2, pt: 2, borderTop: "1px dashed", borderColor: "border.muted" }}>
                    <Text sx={{ fontWeight: "bold", mr: 1 }}>知识点：</Text>
                    {tag.knowledge_points.length > 0 ? (
                      tag.knowledge_points.map((kp) => (
                        <Label key={kp} variant="secondary" sx={{ mr: 1 }}>
                          {kp}
                        </Label>
                      ))
                    ) : (
                      <Text sx={{ color: "fg.muted" }}>未标注</Text>
                    )}
                  </Box>
                )}
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
}
