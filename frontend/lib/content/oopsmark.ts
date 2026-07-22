import type { ContentFormat } from "@/types/api";

/** Compatibility-only normalization for records created before OopsMark v1. */
export function normalizeLegacyContent(text: string): string {
  let normalized = text.replace(/\\\$/g, "$");
  normalized = normalized.replace(/\\(\s*)(?=\n|$)/g, "");
  normalized = normalized.replace(/\\n\\n/g, "\n\n").replace(/\\n/g, "\n");
  normalized = normalized
    .replace(/\\begin\{enumerate\}/g, "")
    .replace(/\\end\{enumerate\}/g, "")
    .replace(/\\item\[(.*?)\]/g, "\n\n$1")
    .replace(/\\item/g, "\n\n")
    .replace(/\\begin\{tabular\}/g, "\\begin{array}")
    .replace(/\\end\{tabular\}/g, "\\end{array}")
    .replace(/(\\begin\{array\}[\s\S]*?\\end\{array\})/g, (match) => `$$${match}$$`)
    .replace(/(\\underline\{\\hspace\{[^}]+\}\})/g, (match) => `$${match}$`);

  const displayMathBlocks: string[] = [];
  normalized = normalized
    .replace(/\$\$([\s\S]*?)\$\$/g, (match) => {
      displayMathBlocks.push(match);
      return `__DISPLAY_MATH_${displayMathBlocks.length - 1}__`;
    })
    .replace(/\\\[([\s\S]*?)\\\]/g, (match) => {
      displayMathBlocks.push(match);
      return `__DISPLAY_MATH_${displayMathBlocks.length - 1}__`;
    });

  normalized = normalized
    .replace(/\$(?!\$)([\s\S]*?)\$/g, (match, inner: string) => {
      if (inner.trim().startsWith("\\displaystyle")) return match;
      return `$\\displaystyle ${inner}$`;
    })
    .replace(/\\\(([\s\S]*?)\\\)/g, (match, inner: string) => {
      if (inner.trim().startsWith("\\displaystyle")) return match;
      return `\\(\\displaystyle ${inner}\\)`;
    });

  displayMathBlocks.forEach((block, index) => {
    normalized = normalized.replace(`__DISPLAY_MATH_${index}__`, block);
  });
  return normalized;
}

export function prepareContentForWeb(text: string, format: ContentFormat): string {
  if (!text) return "";
  if (format === "oopsmark-v1") {
    return text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  }
  return normalizeLegacyContent(text);
}
