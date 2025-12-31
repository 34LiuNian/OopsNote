import type { TagDimension, TagDimensionStyle } from "../../types/api";

export const TAG_DIMENSIONS: Array<{ key: TagDimension; fallbackLabel: string }> = [
  { key: "knowledge", fallbackLabel: "知识体系" },
  { key: "error", fallbackLabel: "错题归因" },
  { key: "meta", fallbackLabel: "题目属性" },
  { key: "custom", fallbackLabel: "自定义" },
];

export function ensureTagDimensionStyles(
  input: Record<string, TagDimensionStyle> | null | undefined
): Record<string, TagDimensionStyle> {
  const out: Record<string, TagDimensionStyle> = { ...(input || {}) };
  for (const d of TAG_DIMENSIONS) {
    out[d.key] = out[d.key] || { label: d.fallbackLabel, label_variant: "secondary" };
  }
  return out;
}
