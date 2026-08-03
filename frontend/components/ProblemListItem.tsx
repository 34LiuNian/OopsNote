"use client";

import Link from "next/link";
import { memo } from "react";
import { Box, Checkbox } from "@/components/ui/primitives";
import type { ProblemSummary } from "../types/api";
import { ProblemCard } from "./ProblemCard";

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
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 3 }}>
      <Box key="problem-content" sx={{ minWidth: 0, flex: 1 }}>
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
          diagramPosition={item.diagram_position}
          diagramScalePercent={item.diagram_scale_percent}
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
      sx={{
        cursor: isSelectable || showViewLink ? "pointer" : "default",
        borderRadius: 2,
        outline: selected ? "1px solid var(--fgColor-accent)" : "none",
        backgroundColor: selected ? "accent.subtle" : "transparent",
        transition: "background-color 0.2s ease-in-out",
        "&:hover": {
          backgroundColor: selected ? "accent.subtle" : "canvas.subtle",
        },
        px: 2,
        py: 2,
      }}
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
        sx={{ display: "flex", alignItems: "flex-start", gap: 3, cursor: "pointer" }}
      >
        <Checkbox
          aria-label={selectionLabel}
          checked={Boolean(selected)}
          onChange={() => onToggleSelection(toggleKey)}
        />
        <Box sx={{ minWidth: 0, flex: 1 }}>{cardContent}</Box>
      </Box>,
    );
  }

  if (showViewLink) {
    return (
      <Link
        href={`/tasks/${item.task_id}`}
        aria-label="查看任务"
        style={{ textDecoration: "none", color: "inherit" }}
      >
        {shell(cardContent)}
      </Link>
    );
  }

  return shell(cardContent);
});
