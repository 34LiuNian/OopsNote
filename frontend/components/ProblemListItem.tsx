"use client";

import Link from "next/link";
import { memo } from "react";
import { Box, Checkbox } from "@primer/react";
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

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: ["1fr", "32px 1fr"],
        gap: 2,
        alignItems: ["center", "center"],
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
        {showCheckbox ? (
          <Checkbox
            aria-label="选择题目"
            checked={!!selected}
            onChange={() => {
              if (toggleKey && onToggleSelection) {
                onToggleSelection(toggleKey);
              }
            }}
          />
        ) : (
          <Box sx={{ width: 16 }} />
        )}
      </Box>

      {showViewLink ? (
        <Link
          href={`/tasks/${item.task_id}`}
          aria-label="查看任务"
          style={{ textDecoration: "none", color: "inherit" }}
        >
          <Box sx={{ cursor: "pointer" }}>
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
          </Box>
        </Link>
      ) : (
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
      )}
    </Box>
  );
});
