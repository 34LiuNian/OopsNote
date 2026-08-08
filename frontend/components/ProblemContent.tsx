"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { Box } from "@/components/ui/primitives";
import { NativeImage } from "@/components/ui/NativeImage";
import { useAuthenticatedAssetUrl } from "@/hooks/useAuthenticatedAssetUrl";
import { MarkdownRenderer } from "./renderers/MarkdownRenderer";
import { SvgMarkup } from "./renderers/SvgMarkup";
import { TikzRenderer } from "./renderers/TikzRenderer";
import { OptionsList } from "./ui/OptionsList";
import { ProblemRenderStatus } from "./ProblemRenderStatus";
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
  const contentRef = useRef<HTMLDivElement | null>(null);
  const illustrationRef = useRef<HTMLElement | null>(null);
  const [contentHeight, setContentHeight] = useState(0);
  const [illustrationAspectRatio, setIllustrationAspectRatio] = useState(1);
  const hasTikz = diagramKind === "tikz" && Boolean(diagramSvg || diagramTikzSource);
  const hasImage = diagramKind === "image" && Boolean(diagramImagePath);
  const hasIllustration = diagramDetected && (hasTikz || hasImage);
  const safeScale = diagramScalePercent == null
    ? 100
    : Math.min(200, Math.max(50, diagramScalePercent));

  useLayoutEffect(() => {
    const element = contentRef.current;
    if (!element || !hasIllustration) {
      setContentHeight(0);
      return;
    }
    const update = () => setContentHeight(element.getBoundingClientRect().height);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasIllustration, problemText, fontSize]);

  useLayoutEffect(() => {
    const element = illustrationRef.current;
    if (!element || !hasIllustration) {
      setIllustrationAspectRatio(1);
      return;
    }

    const update = () => {
      const image = element.querySelector("img");
      if (image?.naturalWidth && image.naturalHeight) {
        setIllustrationAspectRatio(image.naturalWidth / image.naturalHeight);
        return;
      }

      const svg = element.querySelector("svg");
      const viewBox = svg?.viewBox.baseVal;
      if (viewBox?.width && viewBox.height) {
        setIllustrationAspectRatio(viewBox.width / viewBox.height);
      }
    };

    setIllustrationAspectRatio(1);
    update();
    element.addEventListener("load", update, true);
    const observer = new MutationObserver(update);
    observer.observe(element, { childList: true, subtree: true });
    return () => {
      element.removeEventListener("load", update, true);
      observer.disconnect();
    };
  }, [hasIllustration, diagramKind, diagramImagePath, diagramSvg, diagramTikzSource]);

  const imageUrl = useAuthenticatedAssetUrl(diagramImagePath);
  const figureHeight = contentHeight > 0 ? `${contentHeight * safeScale / 100}px` : undefined;

  return (
    <Box>
      <Box className={`problem-content__lead is-${diagramPosition}${hasIllustration ? " has-illustration" : ""}`}>
        <Box ref={contentRef} className="problem-content__body">
          <MarkdownRenderer text={problemText || ""} format={contentFormat} fontSize={fontSize} />
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
        {hasIllustration ? (
          <Box
            ref={illustrationRef}
            as="figure"
            className="problem-content__illustration"
            style={{ height: figureHeight, aspectRatio: illustrationAspectRatio }}
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
      <ProblemRenderStatus
        detected={diagramDetected}
        status={diagramRenderStatus}
        error={diagramError}
        needsReview={diagramNeedsReview}
        retrying={isRetryingDiagram}
        onRetry={onRetryDiagram}
      />
    </Box>
  );
}
