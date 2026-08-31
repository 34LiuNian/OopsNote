"use client";

import { Box, Text } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useRenderErrorNotification } from "@/hooks/useRenderErrorNotification";
import { useLatexAsset } from "@/hooks/useLatexAsset";
import { SvgMarkup } from "./SvgMarkup";
import sxStyles from "./LatexAssetRenderer.sx.module.css";

type LatexAssetRendererProps = {
  kind: "tikz";
  content: string;
  inline?: boolean;
  loadingLabel?: string;
  errorLabel?: string;
  fit?: boolean;
};

export function LatexAssetRenderer({
  kind,
  content,
  inline,
  loadingLabel = "渲染中...",
  errorLabel = "渲染失败",
  fit = false,
}: LatexAssetRendererProps) {
  const { status, data, error } = useLatexAsset({ kind, content, inline });
  useRenderErrorNotification("LaTeX 渲染失败", status === "error" ? (error || errorLabel) : "");

  if (!content) return null;

  if (status === "error") {
    return (
      <Box className={sxStyles.sx1}>
        <ErrorBanner message={error || errorLabel} title="LaTeX 渲染失败" />
      </Box>
    );
  }

  if (status !== "ready") {
    return (
      <Box className={sxStyles.sx3}>
        <Text className={sxStyles.sx4}>{loadingLabel}</Text>
      </Box>
    );
  }

  return (
    <Box className={sxStyles.asset} data-inline={inline ? "true" : "false"} data-fit={fit ? "true" : "false"}>
      <SvgMarkup svg={data} label="后端生成的 TikZ 图形" colorMode="themed" fit={fit} />
    </Box>
  );
}
