import {
  documentRectFromSlices,
  splitSelectionAcrossPages,
  type PageMetric,
  type SelectionModel,
} from "@/components/batch-continuous";
import type { BatchSessionSegment } from "../api";

export function sessionSegmentsToSelections(
  segments: BatchSessionSegment[],
  metrics: PageMetric[],
): SelectionModel[] {
  return segments.flatMap((segment) => {
    const slices = (segment.parts?.length ? segment.parts : [
      segment.page_index !== null && segment.page_index !== undefined && segment.x !== null && segment.x !== undefined
        ? { page_index: segment.page_index, x: segment.x, y: segment.y ?? 0, width: segment.width ?? 0, height: segment.height ?? 0, order: 0 }
        : null,
      segment.continuation ? { ...segment.continuation, order: 1 } : null,
    ].filter(Boolean)).map((part) => ({
      pageId: metrics.find((metric) => metric.pageIndex === part!.page_index)?.id ?? `page-${part!.page_index}`,
      pageIndex: part!.page_index,
      rect: { x: part!.x, y: part!.y, width: part!.width, height: part!.height },
      order: part!.order,
    }));
    const rect = documentRectFromSlices(slices, metrics);
    if (!rect) return [];
    return [{
      id: segment.id,
      start: { x: rect.left, y: rect.top },
      end: { x: rect.right, y: rect.bottom },
      rect,
      slices: splitSelectionAcrossPages(rect, metrics),
      questionNo: segment.question_no ?? 0,
      status: segment.status,
      taskId: segment.task_id ?? undefined,
      problemIds: segment.problem_ids,
      error: segment.error ?? undefined,
    } satisfies SelectionModel];
  });
}

export function selectionsToSessionSegments(selections: SelectionModel[]): BatchSessionSegment[] {
  return selections.map((selection) => ({
    id: selection.id,
    parts: selection.slices.map((slice) => ({
      page_index: slice.pageIndex,
      x: slice.rect.x,
      y: slice.rect.y,
      width: slice.rect.width,
      height: slice.rect.height,
      order: slice.order,
    })),
    question_no: selection.questionNo,
    status: selection.status,
    task_id: selection.taskId ?? null,
    problem_ids: selection.problemIds ?? [],
    error: selection.error ?? null,
  }));
}
