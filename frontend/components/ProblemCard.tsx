"use client";

import { memo } from "react";
import { Box, Text } from "@/components/ui/primitives";
import { ProblemContent } from "./ProblemContent";
import type { ContentFormat, DiagramImageTone } from "@/types/api";
import sxStyles from "./ProblemCard.sx.module.css";

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
  diagramImageTone?: DiagramImageTone;
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
  diagramImageTone,
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
      className={sxStyles.sx1}
    >
      {showTitle && resolvedTitle ? (
        <Text className={sxStyles.sx2}>{resolvedTitle}</Text>
      ) : null}
      {metaParts.length > 0 ? (
        <Text
          className={sxStyles.sx3}
        >
          {metaParts.join(" · ")}
        </Text>
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
        diagramImageTone={diagramImageTone}
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
