"use client";

import { Box } from "@/components/ui/primitives";
import { Button, Spinner } from "@/components/ui/primitives";
import { Text } from "@/components/ui/primitives";
import { InlineMath } from "react-katex";
import { MarkdownRenderer } from "./renderers/MarkdownRenderer";
import { SvgMarkup } from "./renderers/SvgMarkup";
import { TikzRenderer } from "./renderers/TikzRenderer";
import { OptionsList } from "./ui/OptionsList";
import type { ContentFormat } from "@/types/api";

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
  contentFormat = "legacy-markdown-latex",
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
      <MarkdownRenderer text={problemText || ""} format={contentFormat} fontSize={fontSize} />
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
            >
              <SvgMarkup svg={diagramSvg} label="题目图形" />
            </Box>
          ) : diagramKind === "tikz" && diagramTikzSource ? (
            <TikzRenderer code={diagramTikzSource} />
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
              <MarkdownRenderer text={opt.text || ""} format={contentFormat} fontSize={fontSize} />
            )
          }
        />
      ) : null}
    </Box>
  );
}
