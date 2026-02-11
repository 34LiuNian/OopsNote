"use client";

import { Box, Text } from "@primer/react";
import { ProblemContent } from "./ProblemContent";

type ProblemOption = {
  key: string;
  text: string;
  latex_blocks?: string[];
};

type ProblemCardProps = {
  title?: string;
  questionNo?: string | null;
  questionType?: string | null;
  source?: string | null;
  problemText: string;
  options?: ProblemOption[];
  itemKeyPrefix?: string;
  fontSize?: number;
  showMeta?: boolean;
};

function buildMeta(questionType?: string | null, source?: string | null): string[] {
  const parts: string[] = [];
  if (questionType) parts.push(`题型：${questionType}`);
  if (source) parts.push(`来源：${source}`);
  return parts;
}

export function ProblemCard({
  title,
  questionNo,
  questionType,
  source,
  problemText,
  options,
  itemKeyPrefix,
  fontSize,
  showMeta = true,
}: ProblemCardProps) {
  const resolvedTitle = title || (questionNo ? `题号 ${questionNo}` : "");
  const metaParts = showMeta ? buildMeta(questionType, source) : [];

  return (
    <Box
      sx={{
        width: "100%",
        fontFamily: "'Times New Roman','SimSun','宋体',serif",
        "& *": { fontFamily: "'Times New Roman','SimSun','宋体',serif" },
      }}
    >
      {resolvedTitle ? (
        <Text sx={{ fontWeight: "bold", display: "block", mb: 1, fontSize: 2 }}>{resolvedTitle}</Text>
      ) : null}
      {metaParts.length > 0 ? (
        <Text sx={{ color: "fg.muted", fontSize: 1, display: "block", mb: 2 }}>{metaParts.join(" · ")}</Text>
      ) : null}
      <ProblemContent
        problemText={problemText}
        options={options}
        itemKeyPrefix={itemKeyPrefix}
        fontSize={fontSize}
      />
    </Box>
  );
}
