"use client";

import Link from "next/link";
import { memo } from "react";
import { Box, Checkbox } from "@/components/ui/primitives";
import type { ProblemSummary } from "../types/api";
import { ProblemCard } from "./ProblemCard";
import sxStyles from "./ProblemListItem.sx.module.css";

export const ProblemListItem = memo(function ProblemListItem(props: {
  item: ProblemSummary;
  selected?: boolean;
  toggleKey?: string;
  onToggleSelection?: (key: string) => void;
  showViewLink?: boolean;
}) {
  const { item, selected, toggleKey, onToggleSelection, showViewLink = false } = props;
  const isSelectable = Boolean(toggleKey && onToggleSelection);

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
        />
      </Box>
    </Box>
  );

  const shell = (children: React.ReactNode) => (
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
    return shell(
      <Box
        as="label"
        className={sxStyles.sx3}
      >
        <Checkbox
          aria-label={selectionLabel}
          checked={Boolean(selected)}
          onChange={() => onToggleSelection(toggleKey)}
        />
        <Box className={sxStyles.sx4}>{cardContent}</Box>
      </Box>,
    );
  }

  if (showViewLink) {
    return (
      <Link
        href={`/tasks/${item.task_id}`}
        aria-label="查看任务"
        className={sxStyles.link}
      >
        {shell(cardContent)}
      </Link>
    );
  }

  return shell(cardContent);
});
