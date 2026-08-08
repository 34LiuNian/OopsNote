"use client";

import { Box, Text } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useLatexAsset } from "@/hooks/useLatexAsset";
import { SvgMarkup } from "./SvgMarkup";

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

  if (!content) return null;

  if (status === "error") {
    return (
      <Box sx={{ p: 2, border: "1px solid", borderColor: "danger.emphasis", borderRadius: 1, bg: "danger.subtle" }}>
        <ErrorBanner message={error || errorLabel} title="LaTeX 渲染失败" />
        <Text sx={{ color: "danger.fg", fontSize: 1, whiteSpace: "pre-wrap" }}>{error || errorLabel}</Text>
      </Box>
    );
  }

  if (status !== "ready") {
    return (
      <Box sx={{ p: 2, border: "1px dashed", borderColor: "border.default", borderRadius: 1 }}>
        <Text sx={{ color: "fg.muted", fontSize: 1 }}>{loadingLabel}</Text>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: inline ? "inline-flex" : "block",
        alignItems: "center",
        width: fit ? "100%" : undefined,
        height: fit ? "100%" : undefined,
      }}
    >
      <SvgMarkup svg={data} label="后端生成的 TikZ 图形" colorMode="themed" fit={fit} />
    </Box>
  );
}
