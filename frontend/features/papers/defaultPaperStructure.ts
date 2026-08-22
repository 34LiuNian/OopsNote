import type { PaperDraftItem } from "@/types/api";

export const DEFAULT_PAPER_STRUCTURE = [
  { questionType: "单选题", count: 8, points: 5 },
  { questionType: "多选题", count: 3, points: 6 },
  { questionType: "填空题", count: 3, points: 5 },
  { questionType: "解答题", count: 5, points: [13, 15, 15, 17, 17] },
] as const;

export const DEFAULT_REQUESTED_COUNTS = Object.fromEntries(
  DEFAULT_PAPER_STRUCTURE.map(({ questionType, count }) => [questionType, count]),
);

export function defaultPointsFor(
  questionType: string,
  ordinalWithinType: number,
): number | null {
  const structure = DEFAULT_PAPER_STRUCTURE.find(
    (item) => item.questionType === questionType,
  );
  if (!structure) return null;
  return Array.isArray(structure.points)
    ? structure.points[ordinalWithinType] ?? structure.points.at(-1) ?? null
    : structure.points;
}

export function effectiveItemPoints(
  items: PaperDraftItem[],
  index: number,
): number | null {
  const item = items[index];
  if (!item) return null;
  const ordinal = items
    .slice(0, index)
    .filter((candidate) => candidate.question_type === item.question_type)
    .length;
  return item.points ?? defaultPointsFor(item.question_type, ordinal);
}

export function normalizeDefaultPoints(items: PaperDraftItem[]): PaperDraftItem[] {
  const ordinals = new Map<string, number>();
  return items.map((item) => {
    const ordinal = ordinals.get(item.question_type) ?? 0;
    ordinals.set(item.question_type, ordinal + 1);
    return item.points == null
      ? { ...item, points: defaultPointsFor(item.question_type, ordinal) }
      : item;
  });
}
