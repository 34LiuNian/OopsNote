"use client";

import Link from "next/link";
import { memo } from "react";
import { Box } from "@primer/react";
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

  const handleClick = () => {
    if (toggleKey && onToggleSelection) {
      onToggleSelection(toggleKey);
    }
  };

  const cardContent = (
    <ProblemCard
      questionNo={item.question_no}
      questionType={item.question_type}
      source={item.source}
      problemText={item.problem_text || "（无题干）"}
      options={item.options}
      itemKeyPrefix={item.problem_id}
      fontSize={2}
      showTitle={false}
    />
  );

  return (
    <Box
      onClick={handleClick}
      sx={{
        cursor: "pointer",
        borderRadius: 2,
        outline: selected ? "1px solid" : "none",
        outlineColor: "accent.fg",
        backgroundColor: selected ? "accent.subtle" : "transparent",
        transition: "background-color 0.2s ease-in-out",
        "&:hover": {
          backgroundColor: selected ? "accent.subtle" : "canvas.subtle",
        },
        px: 2,
        py: 2,
      }}
    >
      {showViewLink ? (
        <Link
          href={`/tasks/${item.task_id}`}
          aria-label="查看任务"
          style={{ textDecoration: "none", color: "inherit" }}
          onClick={(e) => {
            e.stopPropagation();
            handleClick();
          }}
        >
          {cardContent}
        </Link>
      ) : (
        cardContent
      )}
    </Box>
  );
});
