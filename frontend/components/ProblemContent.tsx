"use client";

import { Box } from "@primer/react";
import { InlineMath } from "react-katex";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { OptionsList } from "./OptionsList";

type ProblemOption = {
  key: string;
  text: string;
  latex_blocks?: string[];
};

type ProblemContentProps = {
  problemText: string;
  options?: ProblemOption[];
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
  itemKeyPrefix,
  fontSize,
  enableInlineMath = true,
}: ProblemContentProps) {
  return (
    <Box>
      <MarkdownRenderer text={problemText || ""} fontSize={fontSize} />
      {options && options.length > 0 ? (
        <OptionsList
          options={options}
          itemKeyPrefix={itemKeyPrefix ?? "problem"}
          renderOptionText={(opt) =>
            enableInlineMath && looksLikeStandaloneMath(opt.text) ? (
              <Box as="span" sx={{ "& .katex": { fontSize: "1.05em" } }}>
                <InlineMath math={normalizeLatexInline(opt.text)} />
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
