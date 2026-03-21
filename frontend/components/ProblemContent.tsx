"use client";

import { Box } from "@primer/react";
import { Button, Spinner } from "@primer/react";
import { Text } from "@primer/react";
import { InlineMath } from "react-katex";
import { MarkdownRenderer } from "./renderers/MarkdownRenderer";
import { LatexAssetRenderer } from "./renderers/LatexAssetRenderer";
import { OptionsList } from "./ui/OptionsList";

type ProblemOption = {
  key: string;
  text: string;
};

type ProblemContentProps = {
  problemText: string;
  options?: ProblemOption[];
  diagramDetected?: boolean;
  diagramKind?: string | null;
  diagramTikzSource?: string | null;
  diagramSvg?: string | null;
  diagramRenderStatus?: string | null;
  diagramError?: string | null;
  diagramNeedsReview?: boolean;
  onRetryDiagram?: () => void;
  isRetryingDiagram?: boolean;
  itemKeyPrefix?: string;
  fontSize?: number;
  enableInlineMath?: boolean;
};

function normalizeLatexInline(input: string): string {
  const trimmed = input.trim();
  if (trimmed.startsWith("$$") && trimmed.endsWith("$$")) {
    return trimmed.slice(2, -2).trim();
  }
  if (trimmed.startsWith("\\[") && trimmed.endsWith("\\]")) {
    return trimmed.slice(2, -2).trim();
  }
  if (trimmed.startsWith("\\(") && trimmed.endsWith("\\)")) {
    return trimmed.slice(2, -2).trim();
  }
  if (trimmed.startsWith("$") && trimmed.endsWith("$")) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

function looksLikeStandaloneMath(input: string): boolean {
  const t = input.trim();
  if (!t) return false;
  if (t.includes("$") || t.includes("\\(") || t.includes("\\[") || t.includes("$$")) return false;
  if (/[\u4e00-\u9fff]/.test(t)) return false;
  if (/\\[a-zA-Z]+/.test(t)) return true;
  return false;
}

export function ProblemContent({
  problemText,
  options,
  diagramDetected = false,
  diagramKind,
  diagramTikzSource,
  diagramSvg,
  diagramRenderStatus,
  diagramError,
  diagramNeedsReview = false,
  onRetryDiagram,
  isRetryingDiagram = false,
  itemKeyPrefix,
  fontSize,
  enableInlineMath = true,
}: ProblemContentProps) {
  return (
    <Box>
      <MarkdownRenderer text={problemText || ""} fontSize={fontSize} />
      {diagramDetected ? (
        <Box sx={{ mt: 2, mb: 2 }}>
          {diagramSvg ? (
            <Box
              sx={{
                p: 2,
                border: "1px solid",
                borderColor: "border.default",
                borderRadius: 1,
                bg: "canvas.subtle",
                "& svg": { maxWidth: "100%", height: "auto" },
              }}
              dangerouslySetInnerHTML={{ __html: diagramSvg }}
            />
          ) : diagramKind === "tikz" && diagramTikzSource ? (
            <LatexAssetRenderer
              kind="tikz"
              content={diagramTikzSource}
              loadingLabel="图形渲染中..."
              errorLabel="图形渲染失败"
            />
          ) : null}

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
                        重试识图中...
                      </>
                    ) : (
                      "重试自动识图"
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
          renderOptionText={(opt) =>
            enableInlineMath && looksLikeStandaloneMath(opt.text) ? (
              <Box as="span" sx={{ "& .katex": { fontSize: "1.05em" } }}>
                <InlineMath math={`\\displaystyle ${normalizeLatexInline(opt.text)}`} />
              </Box>
            ) : (
              <MarkdownRenderer text={opt.text || ""} fontSize={fontSize} />
            )
          }
        />
      ) : null}
    </Box>
  );
}
