import type {
  ContinuousPageSource,
  DocumentCropRect,
  DocumentPoint,
  DocumentRect,
  NormalizedRect,
  PageMetric,
  ResizeHandle,
  SelectionSlice,
} from "./batchContinuousTypes";

export const DOCUMENT_WIDTH = 1000;
export const MIN_CROP_SIZE = 0.05;

export function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function normalizeRect(start: DocumentPoint, end: DocumentPoint): DocumentRect {
  return {
    left: Math.min(start.x, end.x),
    top: Math.min(start.y, end.y),
    right: Math.max(start.x, end.x),
    bottom: Math.max(start.y, end.y),
  };
}

export function buildPageMetrics(
  pages: ContinuousPageSource[],
  crop: DocumentCropRect,
  displayWidth = DOCUMENT_WIDTH,
): PageMetric[] {
  let documentTop = 0;
  return pages.map((page) => {
    const croppedSourceWidth = page.sourceWidth * crop.width;
    const croppedSourceHeight = page.sourceHeight * crop.height;
    const displayHeight = croppedSourceWidth > 0
      ? displayWidth * croppedSourceHeight / croppedSourceWidth
      : 0;
    const metric: PageMetric = {
      ...page,
      crop,
      croppedSourceWidth,
      croppedSourceHeight,
      documentTop,
      documentBottom: documentTop + displayHeight,
      displayWidth,
      displayHeight,
    };
    documentTop = metric.documentBottom;
    return metric;
  });
}

export function clampDocumentPoint(point: DocumentPoint, metrics: PageMetric[]): DocumentPoint {
  const bottom = metrics.at(-1)?.documentBottom ?? 0;
  return {
    x: clamp(point.x, 0, metrics[0]?.displayWidth ?? DOCUMENT_WIDTH),
    y: clamp(point.y, 0, bottom),
  };
}

export function pageToDocumentPoint(page: PageMetric, point: DocumentPoint): DocumentPoint {
  return { x: point.x, y: page.documentTop + point.y };
}

export function documentToPagePoint(page: PageMetric, point: DocumentPoint): DocumentPoint {
  return { x: point.x, y: point.y - page.documentTop };
}

export function intersectSelectionWithPage(selection: DocumentRect, page: PageMetric): SelectionSlice | null {
  const left = clamp(selection.left, 0, page.displayWidth);
  const right = clamp(selection.right, 0, page.displayWidth);
  const top = Math.max(selection.top, page.documentTop);
  const bottom = Math.min(selection.bottom, page.documentBottom);
  if (right <= left || bottom <= top || page.displayHeight <= 0) return null;
  return {
    pageId: page.id,
    pageIndex: page.pageIndex,
    order: 0,
    rect: {
      x: left / page.displayWidth,
      y: (top - page.documentTop) / page.displayHeight,
      width: (right - left) / page.displayWidth,
      height: (bottom - top) / page.displayHeight,
    },
  };
}

export function splitSelectionAcrossPages(selection: DocumentRect, pages: PageMetric[]): SelectionSlice[] {
  return pages.flatMap((page) => {
    const slice = intersectSelectionWithPage(selection, page);
    return slice ? [{ ...slice, order: 0 }] : [];
  }).map((slice, order) => ({ ...slice, order }));
}

export function mapCroppedRectToOriginalSource(rect: NormalizedRect, crop: DocumentCropRect): NormalizedRect {
  return {
    x: crop.x + rect.x * crop.width,
    y: crop.y + rect.y * crop.height,
    width: rect.width * crop.width,
    height: rect.height * crop.height,
  };
}

export function resizeDocumentRect(
  original: DocumentRect,
  handle: ResizeHandle,
  point: DocumentPoint,
  bounds: DocumentRect,
  minimum = 8,
): DocumentRect {
  const next = { ...original };
  if (handle.includes("w")) next.left = clamp(point.x, bounds.left, original.right - minimum);
  if (handle.includes("e")) next.right = clamp(point.x, original.left + minimum, bounds.right);
  if (handle.includes("n")) next.top = clamp(point.y, bounds.top, original.bottom - minimum);
  if (handle.includes("s")) next.bottom = clamp(point.y, original.top + minimum, bounds.bottom);
  return next;
}

export function documentRectFromSlices(slices: SelectionSlice[], metrics: PageMetric[]): DocumentRect | null {
  const rects = slices.flatMap((slice) => {
    const page = metrics.find((metric) => metric.pageIndex === slice.pageIndex);
    if (!page) return [];
    return [{
      left: slice.rect.x * page.displayWidth,
      right: (slice.rect.x + slice.rect.width) * page.displayWidth,
      top: page.documentTop + slice.rect.y * page.displayHeight,
      bottom: page.documentTop + (slice.rect.y + slice.rect.height) * page.displayHeight,
    }];
  });
  if (!rects.length) return null;
  return {
    left: Math.min(...rects.map((rect) => rect.left)),
    top: Math.min(...rects.map((rect) => rect.top)),
    right: Math.max(...rects.map((rect) => rect.right)),
    bottom: Math.max(...rects.map((rect) => rect.bottom)),
  };
}

export function compareDocumentRects(a: DocumentRect, b: DocumentRect) {
  return a.top - b.top || a.left - b.left;
}
