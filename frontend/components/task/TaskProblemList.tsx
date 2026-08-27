"use client";

import { useState } from "react";
import Link from "next/link";
import { Box, Button, Heading, IconButton, Label, Text, Tooltip } from "@/components/ui/primitives";
import { PencilIcon, CopyIcon, ChevronDownIcon, ChevronUpIcon, ZapIcon } from "@/components/ui/icons";
import type { ContentFormat, DiagramImageTone, DiagramPlacement, SourceTrace, TagDimensionStyle } from "@/types/api";
import { MarkdownRenderer } from "../renderers/MarkdownRenderer";
import { ProblemCard } from "../ProblemCard";
import { ProblemEditPanel } from "../ProblemEditPanel";
import { rerenderProblemDiagram } from "@/features/tasks";
import sxStyles from "./TaskProblemList.sx.module.css";

type TaskProblem = {
  problem_id: string;
  subject: string;
  question_no?: string | null;
  chapter?: string | null;
  question_type?: string | null;
  source?: string | null;
  difficulty_coefficient_override?: number | null;
  section_question_count?: number | null;
  difficulty_needs_review?: boolean;
  diagram_detected?: boolean;
  diagram_enabled?: boolean;
  diagram_kind?: string | null;
  diagram_tikz_source?: string | null;
  diagram_svg?: string | null;
  diagram_image_path?: string | null;
  diagram_image_tone?: DiagramImageTone;
  diagram_placement?: DiagramPlacement;
  diagram_scale_adjustment_percent?: number | null;
  diagram_canvas_width_em?: number | null;
  diagram_canvas_height_em?: number | null;
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
  taskAssetPath?: string | null;
  taskTrace?: SourceTrace | null;
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
  onOpenSourceImage?: () => void;
  onOpenVariations?: () => void;
};

export function TaskProblemDetail({
  taskId,
  taskDifficulty,
  taskAssetPath,
  taskTrace,
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
  onOpenSourceImage,
  onOpenVariations,
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
      } else if (problem.diagram_detected && problem.diagram_kind === "image" && problem.diagram_image_path) {
        lines.push("## 附图", `![附图](${problem.diagram_image_path})`, "");
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
      onStatusMessage?.("开始重试图形渲染...");
      await rerenderProblemDiagram(taskId);
      await onSaved();
      onStatusMessage?.("图形渲染已重新排队");
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "图形渲染重试失败");
    }
  };

  const knowledgeTags = Array.isArray(problem?.knowledge_tags) ? problem.knowledge_tags : [];
  const errorTags = Array.isArray(problem?.error_tags) ? problem.error_tags : [];
  const userTags = Array.isArray(problem?.user_tags) ? problem.user_tags : [];
  const aiKnowledge = tag?.knowledge_points || [];
  const allTags = Array.from(new Set([...knowledgeTags, ...errorTags, ...userTags, ...aiKnowledge]));

  return (
    <Box>
      {(!problem || editingKey !== problem.problem_id) && (
        <Heading as="h3" className={sxStyles.sx1}>
          题目与解答
        </Heading>
      )}

      {!problem ? (
        <Box className={["oops-empty-state", sxStyles.sx2].filter(Boolean).join(" ")} >
          <Text as="p" className={sxStyles.sx3}>尚未解析出题目</Text>
          <Text as="p" className={sxStyles.sx4}>如果任务仍在处理中，稍等片刻即可看到结果。</Text>
        </Box>
      ) : (
        <ProblemDetailCard
          problem={problem}
          solution={solution}
          allTags={allTags}
          taskDifficulty={taskDifficulty}
          isEditing={editingKey === problem.problem_id}
          taskId={taskId}
          taskAssetPath={taskAssetPath}
          taskTrace={taskTrace}
          tagStyles={tagStyles}
          onEdit={() => onEdit(problem.problem_id)}
          onCloseEdit={onCloseEdit}
          onSaved={onSaved}
          onCopy={copyMarkdown}
          onRetryDiagram={retryDiagram}
          onOpenSourceImage={onOpenSourceImage}
          onOpenVariations={onOpenVariations}
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
  taskAssetPath,
  taskTrace,
  tagStyles,
  onEdit,
  onCloseEdit,
  onSaved,
  onCopy,
  onRetryDiagram,
  onOpenSourceImage,
  onOpenVariations,
}: {
  problem: TaskProblem;
  solution: TaskSolution | null;
  allTags: string[];
  taskDifficulty?: string | null;
  isEditing: boolean;
  taskId: string;
  taskAssetPath?: string | null;
  taskTrace?: SourceTrace | null;
  tagStyles: Record<string, TagDimensionStyle>;
  onEdit: () => void;
  onCloseEdit: () => void;
  onSaved: () => Promise<void> | void;
  onCopy: () => void;
  onRetryDiagram: () => Promise<void>;
  onOpenSourceImage?: () => void;
  onOpenVariations?: () => void;
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

  if (isEditing) {
    return (
      <ProblemEditPanel
        taskId={taskId}
        problem={problem}
        taskAssetPath={taskAssetPath}
        tagStyles={tagStyles}
        onClose={onCloseEdit}
        onSaved={onSaved}
      />
    );
  }

  return (
    <Box className={["oops-card", sxStyles.sx5].filter(Boolean).join(" ")} >
      <Box
        className={sxStyles.sx6}
      >
        <Box className={sxStyles.sx7}>
          <Text className={sxStyles.sx8}>
          {problem.question_no ? `题 ${problem.question_no}` : "题目"}
          </Text>
          {problem.question_type && <Box className="oops-badge oops-badge-accent">{problem.question_type}</Box>}
          {(problem.source || taskTrace?.source_file_name) && (
            <Text className={sxStyles.sx9}>{problem.source || taskTrace?.source_file_name}</Text>
          )}
          {taskTrace?.kind === "batch_segment" && typeof taskTrace.page_index === "number" && (
            <Text className={sxStyles.sx10}>第 {taskTrace.page_index + 1} 页</Text>
          )}
          {problem.chapter && <Text className={sxStyles.sx11}>章节：{problem.chapter}</Text>}
          {taskDifficulty && <Text className={sxStyles.sx12}>难度：{taskDifficulty}</Text>}
          {taskTrace?.kind === "batch_segment" && taskTrace.source_file_hash && (
            taskTrace.batch_session_available === false ? (
              <span className="task-trace-link is-disabled" aria-disabled="true" title="原批量扫描记录已删除">
                定位到批量扫描
              </span>
            ) : (
              <Link
                href={`/batch-segment?session=${encodeURIComponent(taskTrace.source_file_hash)}&page=${(taskTrace.page_index ?? 0) + 1}`}
                className="task-trace-link"
              >
                定位到批量扫描
              </Link>
            )
          )}
          {taskTrace && onOpenSourceImage && (
            <Button size="small" variant="invisible" onClick={onOpenSourceImage}>
              {taskTrace.kind === "batch_segment" ? "查看选框截图" : "查看原图"}
            </Button>
          )}
        </Box>
        <Box className={sxStyles.sx13}>
          {onOpenVariations && (
            <Button size="small" variant="secondary" onClick={onOpenVariations} leadingVisual={ZapIcon}>
              举一反三
            </Button>
          )}
          <Tooltip text="编辑" direction="s">
            <IconButton icon={PencilIcon} aria-label="编辑" size="small" variant="invisible" onClick={onEdit} />
          </Tooltip>
          <Tooltip text="复制 Markdown" direction="s">
            <IconButton icon={CopyIcon} aria-label="复制" size="small" variant="invisible" onClick={onCopy} />
          </Tooltip>
        </Box>
      </Box>

      <Box className={sxStyles.sx14}>
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
          diagramImagePath={problem.diagram_image_path}
          diagramImageTone={problem.diagram_image_tone}
          diagramPlacement={problem.diagram_placement}
          diagramScaleAdjustmentPercent={problem.diagram_scale_adjustment_percent}
          diagramCanvasWidthEm={problem.diagram_canvas_width_em}
          diagramCanvasHeightEm={problem.diagram_canvas_height_em}
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
        <Box className={sxStyles.sx15}>
          {allTags.map((value) => (
            <Label key={value} variant="secondary" className={sxStyles.sx16}>{value}</Label>
          ))}
        </Box>
      )}

      {solution && (
        <Box className={sxStyles.sx17}>
          <Button
            type="button"
            variant="invisible"
            contentAlign="start"
            onClick={() => setShowAnswer(!showAnswer)}
            className={sxStyles.sx18}
            aria-expanded={showAnswer}
            aria-controls={`task-answer-${problem.problem_id}`}
            trailingVisual={showAnswer ? ChevronUpIcon : ChevronDownIcon}
          >
            {showAnswer ? "收起答案与解析" : "展开答案与解析"}
          </Button>
          {showAnswer && (
            <Box id={`task-answer-${problem.problem_id}`} className={sxStyles.sx20}>
              <Box className={sxStyles.sx21}>
                <Text className={sxStyles.sx22}>答案</Text>
                <MarkdownRenderer text={solution.answer || ""} format={problem.content_format} />
              </Box>
              <Box>
                <Text className={sxStyles.sx23}>解析</Text>
                <MarkdownRenderer text={solution.explanation || ""} format={problem.content_format} />
              </Box>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
