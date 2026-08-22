"use client";

import Link from "next/link";
import { memo, useCallback, useState, type ReactNode } from "react";
import { Eye, EyeOff, RotateCcw } from "lucide-react";
import { Box, Button, Checkbox, Spinner, Text } from "@/components/ui/primitives";
import type { ProblemSummary } from "../types/api";
import { getTask } from "../features/tasks";
import { ProblemCard } from "./ProblemCard";
import { MarkdownRenderer } from "./renderers/MarkdownRenderer";
import sxStyles from "./ProblemListItem.sx.module.css";

type AnswerDetail = {
  answer: string;
  explanation: string;
  contentFormat?: ProblemSummary["content_format"];
};

function keepsAnswerOnOneLine(questionType?: string | null) {
  return questionType === "单选题" || questionType === "多选题";
}

export const ProblemListItem = memo(function ProblemListItem(props: {
  item: ProblemSummary;
  selected?: boolean;
  toggleKey?: string;
  onToggleSelection?: (key: string) => void;
  showViewLink?: boolean;
  header?: ReactNode;
  footer?: ReactNode;
  showMetaPills?: boolean;
  showAnswerPeek?: boolean;
}) {
  const {
    item,
    selected,
    toggleKey,
    onToggleSelection,
    showViewLink = false,
    header,
    footer,
    showMetaPills = false,
    showAnswerPeek = false,
  } = props;
  const isSelectable = Boolean(toggleKey && onToggleSelection);
  const [answerExpanded, setAnswerExpanded] = useState(false);
  const [answer, setAnswer] = useState<AnswerDetail | null>(null);
  const [answerLoading, setAnswerLoading] = useState(false);
  const [answerError, setAnswerError] = useState("");
  const answerPanelId = `problem-answer-${item.problem_id}`;
  const answerNoWrap = keepsAnswerOnOneLine(item.question_type);

  const loadAnswer = useCallback(async (force = false) => {
    if ((answer && !force) || answerLoading) return;
    setAnswerLoading(true);
    setAnswerError("");
    try {
      const response = await getTask(item.task_id);
      const solution = response.task.solution;
      setAnswer({
        answer: solution?.answer ?? "",
        explanation: solution?.explanation ?? "",
        contentFormat: response.task.problem?.content_format ?? item.content_format,
      });
    } catch (reason) {
      setAnswerError(reason instanceof Error ? reason.message : "答案加载失败");
    } finally {
      setAnswerLoading(false);
    }
  }, [answer, answerLoading, item.content_format, item.task_id]);

  const toggleAnswer = useCallback(() => {
    if (answerExpanded) {
      setAnswerExpanded(false);
      return;
    }
    setAnswerExpanded(true);
    void loadAnswer();
  }, [answerExpanded, loadAnswer]);

  const answerControl = showAnswerPeek ? (
    <Button
      size="small"
      variant="invisible"
      leadingVisual={answerExpanded ? EyeOff : Eye}
      className={sxStyles.answerToggle}
      loading={answerLoading}
      aria-expanded={answerExpanded}
      aria-controls={answerPanelId}
      onClick={toggleAnswer}
    >
      {answerExpanded ? "收起答案" : "查看答案"}
    </Button>
  ) : null;

  const answerPanel = showAnswerPeek && answerExpanded ? (
    <Box id={answerPanelId} className={[sxStyles.answerPanel, answerNoWrap ? sxStyles.answerPanelNoWrap : ""].filter(Boolean).join(" ")}>
      {answerError ? (
        <Box className={sxStyles.answerError}>
          <Text>{answerError}</Text>
          <Button size="small" variant="secondary" leadingVisual={RotateCcw} onClick={() => void loadAnswer(true)}>重试</Button>
        </Box>
      ) : answerLoading ? (
        <Box className={sxStyles.answerLoading}><Spinner size="small" /></Box>
      ) : answer?.answer || answer?.explanation ? (
        <Box className={sxStyles.answerSections}>
          <section className={answerNoWrap ? sxStyles.answerValue : undefined}>
            <Text className={sxStyles.answerHeading}>答案</Text>
            <MarkdownRenderer text={answer.answer} format={answer.contentFormat} />
          </section>
          <section>
            <Text className={sxStyles.answerHeading}>解析</Text>
            <MarkdownRenderer text={answer.explanation} format={answer.contentFormat} />
          </section>
        </Box>
      ) : <Text className={sxStyles.answerEmpty}>此题暂无答案与解析。</Text>}
    </Box>
  ) : null;

  const cardContent = (
    <Box className={sxStyles.sx1}>
      <Box key="problem-content" className={sxStyles.sx2}>
        <ProblemCard
          questionNo={item.question_no}
          questionType={item.question_type}
          source={item.source}
          problemText={item.problem_text || "（无题干）"}
          contentFormat={item.content_format}
          options={item.options}
          diagramDetected={item.diagram_detected}
          diagramKind={item.diagram_kind}
          diagramTikzSource={item.diagram_tikz_source}
          diagramSvg={item.diagram_svg}
          diagramImagePath={item.diagram_image_path}
          diagramImageTone={item.diagram_image_tone}
          diagramPlacement={item.diagram_placement}
          diagramScaleAdjustmentPercent={item.diagram_scale_adjustment_percent}
          diagramCanvasWidthEm={item.diagram_canvas_width_em}
          diagramCanvasHeightEm={item.diagram_canvas_height_em}
          diagramRenderStatus={item.diagram_render_status}
          diagramError={item.diagram_error}
          diagramNeedsReview={item.diagram_needs_review}
          itemKeyPrefix={item.problem_id}
          fontSize={2}
          showTitle={false}
          showMeta={!header && !showMetaPills}
        />
      </Box>
    </Box>
  );

  const headerContent = header ? <Box>{header}</Box> : (showMetaPills || showAnswerPeek ? (
    <Box className={sxStyles.metaRow}>
      <Box className={sxStyles.metaPills}>
        {item.question_type ? <span className={sxStyles.metaPill}>{item.question_type}</span> : null}
        {item.source ? <span className={sxStyles.metaPill}>{item.source}</span> : null}
      </Box>
      {answerControl}
    </Box>
  ) : null);
  const footerContent = (
    <>
      {answerPanel}
      {footer ? <Box>{footer}</Box> : null}
    </>
  );

  const shell = (children: ReactNode) => (
    <Box
      className={sxStyles.shell}
      data-interactive={isSelectable || showViewLink ? "true" : undefined}
      data-selected={selected ? "true" : undefined}
    >
      {children}
    </Box>
  );

  if (isSelectable && toggleKey && onToggleSelection) {
    const selectionLabel = item.question_no
      ? `选择题目 ${item.question_no}`
      : `选择题目 ${item.problem_id}`;
    return shell(<>
      {headerContent}
      <Box as="label" className={sxStyles.sx3}>
        <Checkbox aria-label={selectionLabel} checked={Boolean(selected)} onChange={() => onToggleSelection(toggleKey)} />
        <Box className={sxStyles.sx4}>{cardContent}</Box>
      </Box>
      {footerContent}
    </>);
  }

  if (showViewLink) {
    return (
      shell(<>
        {headerContent}
        <Link href={`/tasks/${item.task_id}`} aria-label="查看任务" className={sxStyles.link}>
          {cardContent}
        </Link>
        {footerContent}
      </>)
    );
  }

  return shell(<>{headerContent}{cardContent}{footerContent}</>);
});
