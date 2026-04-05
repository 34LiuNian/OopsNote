import type { TagItem } from "../../types/api";

function normalized(value: string): string {
  return String(value || "").trim().toLowerCase();
}

function scoreItem(item: TagItem, query: string): number {
  const q = normalized(query);
  if (!q) return Number(item.ref_count || 0);

  const value = normalized(item.value);
  const aliases = Array.isArray(item.aliases) ? item.aliases.map((it) => normalized(String(it))) : [];

  // Keep this scoring simple and deterministic for predictable UX.
  if (value === q || aliases.includes(q)) return 10_000 + Number(item.ref_count || 0);
  if (value.startsWith(q) || aliases.some((a) => a.startsWith(q))) return 8_000 + Number(item.ref_count || 0);
  if (value.includes(q) || aliases.some((a) => a.includes(q))) return 5_000 + Number(item.ref_count || 0);

  return Number(item.ref_count || 0);
}

export function sortTagItemsByQuery(items: TagItem[], query: string): TagItem[] {
  const q = normalized(query);
  return [...items].sort((a, b) => {
    const diff = scoreItem(b, q) - scoreItem(a, q);
    if (diff !== 0) return diff;
    return String(a.value || "").localeCompare(String(b.value || ""), "zh-CN");
  });
}
