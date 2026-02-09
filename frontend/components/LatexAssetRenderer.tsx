"use client";

import { Box, Text } from "@primer/react";
import { useLatexAsset } from "../hooks/useLatexAsset";

type LatexAssetRendererProps = {
  kind: "chemfig" | "tikz";
  content: string;
  inline?: boolean;
  loadingLabel?: string;
  errorLabel?: string;
};

export function LatexAssetRenderer({
  kind,
  content,
  inline,
  loadingLabel = "渲染中...",
  errorLabel = "渲染失败",
}: LatexAssetRendererProps) {
  const { status, data, error } = useLatexAsset({ kind, content, inline });

  if (!content) return null;

  if (status === "error") {
    return (
      <Box sx={{ p: 2, border: "1px solid", borderColor: "danger.emphasis", borderRadius: 1, bg: "danger.subtle" }}>
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
      }}
      dangerouslySetInnerHTML={{ __html: data }}
    />
  );
}
