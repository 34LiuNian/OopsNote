"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { Box } from "@/components/ui/primitives";
import { Button, Spinner } from "@/components/ui/primitives";
import { Text } from "@/components/ui/primitives";
import { NativeImage } from "@/components/ui/NativeImage";
import { MarkdownRenderer } from "./renderers/MarkdownRenderer";
import { SvgMarkup } from "./renderers/SvgMarkup";
import { TikzRenderer } from "./renderers/TikzRenderer";
import { OptionsList } from "./ui/OptionsList";
import type { ContentFormat, DiagramImageTone } from "@/types/api";

type ProblemOption = {
  key: string;
  text: string;
};

type ProblemContentProps = {
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
};

export function ProblemContent({
  problemText,
  contentFormat = "legacy-markdown-latex",
  options,
  diagramDetected = false,
  diagramKind,
  diagramTikzSource,
  diagramSvg,
  diagramImagePath,
  diagramImageTone = "auto",
  diagramPosition = "right",
  diagramScalePercent = null,
  diagramRenderStatus,
  diagramError,
  diagramNeedsReview = false,
  onRetryDiagram,
  isRetryingDiagram = false,
  itemKeyPrefix,
  fontSize,
}: ProblemContentProps) {
  const textRef = useRef<HTMLDivElement | null>(null);
  const [textHeight, setTextHeight] = useState(0);
  const hasTikz = diagramKind === "tikz" && Boolean(diagramSvg || diagramTikzSource);
  const hasImage = diagramKind === "image" && Boolean(diagramImagePath);
  const hasIllustration = diagramDetected && (hasTikz || hasImage);
  const safeScale = diagramScalePercent == null
    ? 100
    : Math.min(200, Math.max(50, diagramScalePercent));

  useLayoutEffect(() => {
    const element = textRef.current;
    if (!element || !hasIllustration) {
      setTextHeight(0);
      return;
    }
    const update = () => setTextHeight(element.getBoundingClientRect().height);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasIllustration, problemText, fontSize]);

  const imageUrl = diagramImagePath
    ? diagramImagePath.startsWith("/assets/") ? `/api${diagramImagePath}` : diagramImagePath
    : "";
  const figureHeight = textHeight > 0 ? `${textHeight * safeScale / 100}px` : undefined;

  return (
    <Box>
      <Box className={`problem-content__lead is-${diagramPosition}${hasIllustration ? " has-illustration" : ""}`}>
        <Box ref={textRef} className="problem-content__text">
          <MarkdownRenderer text={problemText || ""} format={contentFormat} fontSize={fontSize} />
        </Box>
        {hasIllustration ? (
          <Box
            as="figure"
            className="problem-content__illustration"
            style={{ height: figureHeight }}
            sx={{ m: 0 }}
          >
            {diagramKind === "image" && imageUrl ? (
              <NativeImage className={diagramImageTone === "auto" ? "is-auto-tone" : undefined} src={imageUrl} alt="附图" />
            ) : diagramSvg ? (
              <SvgMarkup svg={diagramSvg} label="题目图形" colorMode="themed" fit />
            ) : diagramTikzSource ? (
              <TikzRenderer code={diagramTikzSource} fit />
            ) : null}
          </Box>
        ) : null}
      </Box>
      {diagramDetected ? (
        <Box sx={{ mb: 2 }}>
          {(diagramRenderStatus === "failed" || diagramNeedsReview) && (
            <Box sx={{ mt: 2, p: 2, border: "1px solid", borderColor: "attention.emphasis", borderRadius: 1, bg: "attention.subtle" }}>
              <Text sx={{ color: "attention.fg", fontSize: 1 }}>
                图形重建失败，建议人工介入。
              </Text>
              {diagramError ? (
                <Text sx={{ display: "block", mt: 1, color: "fg.muted", fontSize: 0, whiteSpace: "pre-wrap" }}>
                  {diagramError}
                </Text>
              ) : null}
              {onRetryDiagram ? (
                <Box sx={{ mt: 2 }}>
                  <Button size="small" variant="default" onClick={onRetryDiagram} disabled={isRetryingDiagram}>
                    {isRetryingDiagram ? (
                      <>
                        <Spinner size="small" sx={{ mr: 1 }} />
                        重试渲染中...
                      </>
                    ) : (
                      "重试图形渲染"
                    )}
                  </Button>
                </Box>
              ) : null}
            </Box>
          )}
        </Box>
      ) : null}
      {options && options.length > 0 ? (
        <OptionsList
          options={options}
          itemKeyPrefix={itemKeyPrefix ?? "problem"}
          renderOptionText={(opt) => (
            <MarkdownRenderer text={opt.text || ""} format={contentFormat} fontSize={fontSize} />
          )}
        />
      ) : null}
    </Box>
  );
}
