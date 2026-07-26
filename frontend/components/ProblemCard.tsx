"use client";

import { memo } from "react";
import { Box, Text } from "@/components/ui/primitives";
import { ProblemContent } from "./ProblemContent";
import type { ContentFormat } from "@/types/api";

type ProblemOption = {
  key: string;
  text: string;
};

type ProblemCardProps = {
  title?: string;
  questionNo?: string | null;
  questionType?: string | null;
  source?: string | null;
  problemText: string;
  contentFormat?: ContentFormat;
  options?: ProblemOption[];
  diagramDetected?: boolean;
  diagramKind?: string | null;
  diagramTikzSource?: string | null;
  diagramSvg?: string | null;
  diagramImagePath?: string | null;
  diagramPosition?: "left" | "right";
  diagramScalePercent?: number | null;
  diagramRenderStatus?: string | null;
  diagramError?: string | null;
  diagramNeedsReview?: boolean;
  onRetryDiagram?: () => void;
  isRetryingDiagram?: boolean;
  itemKeyPrefix?: string;
  fontSize?: number;
  showTitle?: boolean;
  showMeta?: boolean;
};

function buildMeta(questionType?: string | null, source?: string | null): string[] {
  const parts: string[] = [];
  if (questionType) parts.push(`题型：${questionType}`);
  if (source) parts.push(`来源：${source}`);
  return parts;
}

export const ProblemCard = memo(function ProblemCard({
  title,
  questionNo,
  questionType,
  source,
  problemText,
  contentFormat,
  options,
  diagramDetected,
  diagramKind,
  diagramTikzSource,
  diagramSvg,
  diagramImagePath,
  diagramPosition,
  diagramScalePercent,
  diagramRenderStatus,
  diagramError,
  diagramNeedsReview,
  onRetryDiagram,
  isRetryingDiagram,
  itemKeyPrefix,
  fontSize,
  showTitle = true,
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
      {showTitle && resolvedTitle ? (
        <Text sx={{ fontWeight: "bold", display: "block", mb: 1, fontSize: 2 }}>{resolvedTitle}</Text>
      ) : null}
      {metaParts.length > 0 ? (
        <Text sx={{ color: "fg.muted", fontSize: 0, display: "block", mb: 2 }}>{metaParts.join(" · ")}</Text>
      ) : null}
      <ProblemContent
        problemText={problemText}
        contentFormat={contentFormat}
        options={options}
        diagramDetected={diagramDetected}
        diagramKind={diagramKind}
        diagramTikzSource={diagramTikzSource}
        diagramSvg={diagramSvg}
        diagramImagePath={diagramImagePath}
        diagramPosition={diagramPosition}
        diagramScalePercent={diagramScalePercent}
        diagramRenderStatus={diagramRenderStatus}
        diagramError={diagramError}
        diagramNeedsReview={diagramNeedsReview}
        onRetryDiagram={onRetryDiagram}
        isRetryingDiagram={isRetryingDiagram}
        itemKeyPrefix={itemKeyPrefix}
        fontSize={fontSize}
      />
    </Box>
  );
});
