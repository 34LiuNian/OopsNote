"use client";

import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Box } from "@/components/ui/primitives";
import { NativeImage } from "@/components/ui/NativeImage";
import { useAuthenticatedAssetUrl } from "@/hooks/useAuthenticatedAssetUrl";
import { MarkdownRenderer } from "./renderers/MarkdownRenderer";
import { SvgMarkup } from "./renderers/SvgMarkup";
import { TikzRenderer } from "./renderers/TikzRenderer";
import { OptionsList } from "./ui/OptionsList";
import { ProblemRenderStatus } from "./ProblemRenderStatus";
import type { ContentFormat, DiagramImageTone, DiagramPlacement } from "@/types/api";
import sxStyles from "./ProblemContent.sx.module.css";

type ProblemOption = { key: string; text: string };

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
  diagramPlacement?: DiagramPlacement;
  diagramScaleAdjustmentPercent?: number | null;
  diagramCanvasWidthEm?: number | null;
  diagramCanvasHeightEm?: number | null;
  diagramRenderStatus?: string | null;
  diagramError?: string | null;
  diagramNeedsReview?: boolean;
  onRetryDiagram?: () => void;
  isRetryingDiagram?: boolean;
  itemKeyPrefix?: string;
  fontSize?: number;
};

const DEFAULT_PLACEMENT: DiagramPlacement = { kind: "side", side: "right" };

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
  diagramPlacement = DEFAULT_PLACEMENT,
  diagramScaleAdjustmentPercent = 100,
  diagramCanvasWidthEm,
  diagramCanvasHeightEm,
  diagramRenderStatus,
  diagramError,
  diagramNeedsReview = false,
  onRetryDiagram,
  isRetryingDiagram = false,
  itemKeyPrefix,
  fontSize,
}: ProblemContentProps) {
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const stemRef = useRef<HTMLDivElement | null>(null);
  const illustrationRef = useRef<HTMLElement | null>(null);
  const [stemHeight, setStemHeight] = useState(0);
  const [assetAspectRatio, setAssetAspectRatio] = useState(1);
  const [sideFits, setSideFits] = useState(true);
  const hasTikz = diagramKind === "tikz" && Boolean(diagramSvg || diagramTikzSource);
  const hasImage = diagramKind === "image" && Boolean(diagramImagePath);
  const hasIllustration = diagramDetected && (hasTikz || hasImage);
  const hasNormalizedTikz = hasTikz
    && typeof diagramCanvasWidthEm === "number"
    && diagramCanvasWidthEm > 0
    && typeof diagramCanvasHeightEm === "number"
    && diagramCanvasHeightEm > 0;
  const safeAdjustment = Math.min(200, Math.max(50, diagramScaleAdjustmentPercent ?? 100));
  const normalizedWidthEm = hasNormalizedTikz ? diagramCanvasWidthEm * safeAdjustment / 100 : null;
  const normalizedHeightEm = hasNormalizedTikz ? diagramCanvasHeightEm * safeAdjustment / 100 : null;
  const normalizedAspectRatio = hasNormalizedTikz
    ? diagramCanvasWidthEm / diagramCanvasHeightEm
    : null;

  useLayoutEffect(() => {
    const element = stemRef.current;
    if (!element || !hasIllustration || hasNormalizedTikz) {
      return;
    }
    const update = () => setStemHeight(element.getBoundingClientRect().height);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasIllustration, hasNormalizedTikz, problemText, fontSize]);

  useLayoutEffect(() => {
    if (normalizedAspectRatio) return;
    const element = illustrationRef.current;
    if (!element || !hasIllustration) return;
    const update = () => {
      const image = element.querySelector("img");
      if (image?.naturalWidth && image.naturalHeight) {
        setAssetAspectRatio(image.naturalWidth / image.naturalHeight);
        return;
      }
      const svg = element.querySelector("svg");
      const viewBox = svg?.viewBox.baseVal;
      if (viewBox?.width && viewBox.height) setAssetAspectRatio(viewBox.width / viewBox.height);
    };
    const animationFrame = window.requestAnimationFrame(update);
    element.addEventListener("load", update, true);
    const observer = new MutationObserver(update);
    observer.observe(element, { childList: true, subtree: true });
    return () => {
      window.cancelAnimationFrame(animationFrame);
      element.removeEventListener("load", update, true);
      observer.disconnect();
    };
  }, [diagramImagePath, diagramSvg, diagramTikzSource, hasIllustration, normalizedAspectRatio]);

  useLayoutEffect(() => {
    const element = layoutRef.current;
    if (!element || diagramPlacement.kind !== "side" || normalizedWidthEm == null) {
      return;
    }
    const update = () => {
      const fontSizePx = Number.parseFloat(window.getComputedStyle(element).fontSize) || 16;
      const requiredWidth = normalizedWidthEm * fontSizePx + 24 + 260;
      setSideFits(element.clientWidth >= requiredWidth);
    };
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [diagramPlacement, normalizedWidthEm]);

  const effectivePlacement: DiagramPlacement = diagramPlacement.kind === "side"
    && normalizedWidthEm != null
    && !sideFits
    ? { kind: "block", anchor: "after_options", align: diagramPlacement.side }
    : diagramPlacement;
  const imageUrl = useAuthenticatedAssetUrl(diagramImagePath);
  const illustrationStyle: CSSProperties = {
    aspectRatio: hasNormalizedTikz ? undefined : assetAspectRatio,
    width: normalizedWidthEm == null ? undefined : `${normalizedWidthEm}em`,
    height: normalizedHeightEm != null
      ? `${normalizedHeightEm}em`
      : stemHeight > 0
        ? `${stemHeight * safeAdjustment / 100}px`
        : undefined,
  };

  const tikzMarkup = diagramSvg ? (
    <SvgMarkup svg={diagramSvg} label="题目图形" colorMode="themed" fit />
  ) : diagramTikzSource ? (
    <TikzRenderer code={diagramTikzSource} fit />
  ) : null;

  const illustration = hasIllustration ? (
    <Box
      key="illustration"
      ref={illustrationRef}
      as="figure"
      className={["problem-content__illustration", sxStyles.sx1].filter(Boolean).join(" ")}
      data-normalized-tikz={hasNormalizedTikz ? "true" : "false"}
      style={illustrationStyle}
    >
      {diagramKind === "image" && imageUrl ? (
        <NativeImage className={diagramImageTone === "auto" ? "is-auto-tone" : undefined} src={imageUrl} alt="附图" />
      ) : hasNormalizedTikz && normalizedWidthEm != null && normalizedHeightEm != null ? (
        <Box
          className="problem-content__illustration-canvas"
          style={{ width: `${normalizedWidthEm}em`, height: `${normalizedHeightEm}em` }}
        >
          {tikzMarkup}
        </Box>
      ) : tikzMarkup}
    </Box>
  ) : null;

  const stem = (
    <Box key="stem" ref={stemRef} className="problem-content__stem">
      <MarkdownRenderer text={problemText || ""} format={contentFormat} fontSize={fontSize} />
    </Box>
  );
  const optionList = options && options.length > 0 ? (
    <Box key="options" className="problem-content__options">
      <OptionsList
        options={options}
        itemKeyPrefix={itemKeyPrefix ?? "problem"}
        renderOptionText={(opt) => (
          <MarkdownRenderer text={opt.text || ""} format={contentFormat} fontSize={fontSize} />
        )}
      />
    </Box>
  ) : null;

  const blocks: ReactNode[] = [stem];
  if (effectivePlacement.kind === "block" && effectivePlacement.anchor === "after_stem") blocks.push(illustration);
  if (optionList) blocks.push(optionList);
  if (effectivePlacement.kind === "side" || (effectivePlacement.kind === "block" && effectivePlacement.anchor === "after_options")) blocks.push(illustration);

  return (
    <Box className="problem-content" data-font-size={fontSize ?? 1}>
      <Box
        ref={layoutRef}
        className={`problem-content__layout${hasIllustration ? " has-illustration" : ""}`}
        data-placement={effectivePlacement.kind}
        data-side={effectivePlacement.kind === "side" ? effectivePlacement.side : undefined}
        data-align={effectivePlacement.kind === "block" ? effectivePlacement.align : undefined}
      >
        {blocks}
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
