import { buildPageMetrics, compareDocumentRects, type ColumnLayout, type ContinuousPageSource, type DocumentCropRect, type SelectionModel, type SelectionReviewReason } from "@/components/batch-continuous";
import { selectionsToSessionSegments, sessionSegmentsToSelections } from "../adapters/batchSessionSelectionAdapter";
import type { BatchSession } from "../api";

export type PdfPageHandle = {
  getViewport: (options: { scale: number }) => { width: number; height: number };
  render: (options: { canvasContext: CanvasRenderingContext2D; viewport: { width: number; height: number } }) => { promise: Promise<unknown> };
};
export type PdfDocumentHandle = {
  numPages: number;
  getPage: (pageNumber: number) => Promise<PdfPageHandle>;
  destroy?: () => Promise<void>;
};
export type PdfResource = { document: PdfDocumentHandle; url: string };
export type SaveState = "idle" | "saving" | "saved" | "failed";

export const FULL_CROP: DocumentCropRect = { x: 0, y: 0, width: 1, height: 1 };
export const PAGE_CACHE_LIMIT = 6;
export const REVIEW_REASON_LABELS: Record<SelectionReviewReason, string> = {
  unreadable: "扫不到题",
  incomplete: "题目区域不完整",
  multiple_questions: "包含多道完整题目",
  other: "其他异常",
};

export function isPdf(file: File) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

export async function hashFile(file: File) {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

export function summarizeBatchSession(session: BatchSession) {
  return session.segments.reduce(
    (counts, segment) => {
      if (segment.status === "completed") counts.completed += 1;
      else if (segment.status === "processing") counts.processing += 1;
      else if (segment.status === "pending") counts.pending += 1;
      else if (segment.status === "failed" || segment.status === "needs_review") counts.failed += 1;
      return counts;
    },
    { completed: 0, processing: 0, pending: 0, failed: 0 },
  );
}

export function upsertBatchSession(sessions: BatchSession[], session: BatchSession) {
  return [session, ...sessions.filter((item) => item.file_hash !== session.file_hash)]
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
}

export function buildSessionContentSnapshot(
  pageCount: number,
  crop: DocumentCropRect,
  cropConfirmed: boolean,
  columnLayout: ColumnLayout,
  excludedPageIndices: number[],
  selections: SelectionModel[],
) {
  return JSON.stringify({
    page_count: pageCount,
    crop_rect: crop,
    crop_confirmed: cropConfirmed,
    column_layout: { column_count: columnLayout.columnCount, overlap_ratio: columnLayout.overlapRatio },
    excluded_page_indices: [...excludedPageIndices].sort((a, b) => a - b),
    segments: selectionsToSessionSegments(selections),
  });
}

export async function openPdf(file: File): Promise<PdfResource> {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/legacy/build/pdf.worker.min.mjs", import.meta.url).toString();
  const url = URL.createObjectURL(file);
  try {
    const document = await pdfjs.getDocument({ url }).promise;
    return { document: document as unknown as PdfDocumentHandle, url };
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
}

export async function renderPdfPage(pdfDocument: PdfDocumentHandle, pageIndex: number, filename: string) {
  const page = await pdfDocument.getPage(pageIndex + 1);
  const viewport = page.getViewport({ scale: 1.5 });
  const output = document.createElement("canvas");
  output.width = Math.ceil(viewport.width);
  output.height = Math.ceil(viewport.height);
  const context = output.getContext("2d");
  if (!context) throw new Error("无法创建 PDF 页面画布");
  await page.render({ canvasContext: context, viewport }).promise;
  const blob = await new Promise<Blob>((resolve, reject) => {
    output.toBlob((value) => value ? resolve(value) : reject(new Error("无法渲染 PDF 页面")), "image/png");
  });
  return new File([blob], `${filename}-page-${pageIndex + 1}.png`, { type: "image/png" });
}

export function sortAndNumber(selections: SelectionModel[]) {
  const sorted = [...selections].sort((a, b) => compareDocumentRects(a.rect, b.rect));
  const lockedNumbers = new Set(sorted.filter((selection) => selection.status !== "pending").map((selection) => selection.questionNo));
  let candidate = 1;
  return sorted.map((selection) => {
    if (selection.status !== "pending") return selection;
    while (lockedNumbers.has(candidate)) candidate += 1;
    const questionNo = candidate;
    candidate += 1;
    return { ...selection, questionNo };
  });
}

export function selectionLocationLabel(selection: SelectionModel, columnCount: number) {
  const parts = [...selection.slices].sort((a, b) => a.order - b.order);
  const first = parts[0];
  const last = parts.at(-1);
  if (!first || !last) return "位置未知";
  if (columnCount === 1) return first.pageIndex === last.pageIndex ? `第 ${first.pageIndex + 1} 页` : `第 ${first.pageIndex + 1}–${last.pageIndex + 1} 页`;
  if (first.pageIndex === last.pageIndex) {
    if (first.columnIndex === last.columnIndex) return `第 ${first.pageIndex + 1} 页 · 第 ${first.columnIndex + 1} 栏`;
    return `第 ${first.pageIndex + 1} 页 · 第 ${first.columnIndex + 1}–${last.columnIndex + 1} 栏`;
  }
  return `第 ${first.pageIndex + 1} 页第 ${first.columnIndex + 1} 栏–第 ${last.pageIndex + 1} 页第 ${last.columnIndex + 1} 栏`;
}

export function nearestAvailablePageIndex(pages: Array<{ pageIndex: number }>, excludedPageIndices: number[], requested: number) {
  const excluded = new Set(excludedPageIndices);
  const available = pages.filter((page) => !excluded.has(page.pageIndex));
  if (!available.length) return 0;
  return [...available].sort((a, b) => Math.abs(a.pageIndex - requested) - Math.abs(b.pageIndex - requested) || a.pageIndex - b.pageIndex)[0].pageIndex;
}

export function projectBatchSession(session: BatchSession, pages: ContinuousPageSource[]) {
  const columnLayout: ColumnLayout = {
    columnCount: session.column_layout?.column_count ?? 1,
    overlapRatio: session.column_layout?.overlap_ratio ?? 0.5,
  };
  const activePages = pages.filter(
    (page) => !(session.excluded_page_indices ?? []).includes(page.pageIndex),
  );
  const selections = sortAndNumber(sessionSegmentsToSelections(
    session.segments,
    buildPageMetrics(activePages, session.crop_rect, columnLayout),
  ));
  const snapshot = buildSessionContentSnapshot(
    session.page_count,
    session.crop_rect,
    session.crop_confirmed,
    columnLayout,
    session.excluded_page_indices ?? [],
    selections,
  );
  return { columnLayout, selections, snapshot };
}
