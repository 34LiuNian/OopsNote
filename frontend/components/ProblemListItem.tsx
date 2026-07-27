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
  showCheckbox?: boolean;
  showViewLink?: boolean;
}) {
  const { item, selected, toggleKey, onToggleSelection, showCheckbox = false, showViewLink = false } = props;
  const isSelectable = Boolean(toggleKey && onToggleSelection);

  const handleClick = () => {
    if (toggleKey && onToggleSelection) {
      onToggleSelection(toggleKey);
    }
  };

  const cardContent = (
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 3 }}>
      {showCheckbox && (
        <Box sx={{ mt: 1, flexShrink: 0 }}>
          <Checkbox
            aria-label={`选择题目${item.question_no ? ` ${item.question_no}` : ""}`}
            checked={Boolean(selected)}
            onClick={(event) => event.stopPropagation()}
            onChange={handleClick}
          />
        </Box>
      )}
      <Box sx={{ minWidth: 0, flex: 1 }}>
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

  const selectableCard = (
    <Box
      role={isSelectable ? "button" : undefined}
      tabIndex={isSelectable ? 0 : undefined}
      aria-pressed={isSelectable ? Boolean(selected) : undefined}
      onClick={isSelectable ? handleClick : undefined}
      onKeyDown={isSelectable ? (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        handleClick();
      } : undefined}
      sx={{
        cursor: isSelectable ? "pointer" : "default",
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
      {cardContent}
    </Box>
  );

  return showViewLink ? (
    <Link
      href={`/tasks/${item.task_id}`}
      aria-label="查看任务"
      style={{ textDecoration: "none", color: "inherit" }}
    >
      {selectableCard}
    </Link>
  ) : selectableCard;
});
