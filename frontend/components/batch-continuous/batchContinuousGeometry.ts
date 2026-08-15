import type {
  ContinuousPageSource,
  ColumnLayout,
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
export const DEFAULT_COLUMN_LAYOUT: ColumnLayout = { columnCount: 1, overlapRatio: 0.5 };

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
  columnLayout: ColumnLayout = DEFAULT_COLUMN_LAYOUT,
  displayWidth = DOCUMENT_WIDTH,
): PageMetric[] {
  const columnCount = Math.max(1, Math.floor(columnLayout.columnCount));
  const overlapRatio = clamp(columnLayout.overlapRatio, 0, 0.5);
  let documentTop = 0;
  let readingIndex = 0;
  return pages.flatMap((page) => Array.from({ length: columnCount }, (_, columnIndex) => {
    const coreWidth = crop.width / columnCount;
    const coreRect: NormalizedRect = {
      x: crop.x + columnIndex * coreWidth,
      y: crop.y,
      width: coreWidth,
      height: crop.height,
    };
    const borrowedWidth = coreWidth * overlapRatio;
    const viewLeft = Math.max(crop.x, coreRect.x - borrowedWidth);
    const viewRight = Math.min(crop.x + crop.width, coreRect.x + coreRect.width + borrowedWidth);
    const viewRect: NormalizedRect = {
      x: viewLeft,
      y: crop.y,
      width: viewRight - viewLeft,
      height: crop.height,
    };
    const coreDisplayWidth = columnCount === 1 ? displayWidth : displayWidth / 2;
    const coreDisplayLeft = columnCount === 1 ? 0 : (displayWidth - coreDisplayWidth) / 2;
    const coreSourceWidth = page.sourceWidth * coreRect.width;
    const sourceScale = coreSourceWidth > 0 ? coreDisplayWidth / coreSourceWidth : 0;
    const croppedSourceWidth = page.sourceWidth * viewRect.width;
    const croppedSourceHeight = page.sourceHeight * crop.height;
    const displayHeight = croppedSourceHeight * sourceScale;
    const contentLeft = coreDisplayLeft + (viewRect.x - coreRect.x) * page.sourceWidth * sourceScale;
    const contentRight = contentLeft + croppedSourceWidth * sourceScale;
    const metric: PageMetric = {
      ...page,
      id: `${page.id}-column-${columnIndex}`,
      sourcePageId: page.id,
      label: columnCount === 1 ? page.label : `${page.label} · 第 ${columnIndex + 1} 栏`,
      columnIndex,
      columnCount,
      readingIndex,
      crop,
      coreRect,
      viewRect,
      croppedSourceWidth,
      croppedSourceHeight,
      documentTop,
      documentBottom: documentTop + displayHeight,
      displayWidth,
      displayHeight,
      coreDisplayLeft,
      coreDisplayWidth,
      contentLeft,
      contentRight,
      sourceScale,
    };
    documentTop = metric.documentBottom;
    readingIndex += 1;
    return metric;
  }));
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
  const left = clamp(selection.left, page.contentLeft, page.contentRight);
  const right = clamp(selection.right, page.contentLeft, page.contentRight);
  const top = Math.max(selection.top, page.documentTop);
  const bottom = Math.min(selection.bottom, page.documentBottom);
  if (right <= left || bottom <= top || page.displayHeight <= 0) return null;
  const sourceLeft = page.coreRect.x + (left - page.coreDisplayLeft) / (page.sourceWidth * page.sourceScale);
  const sourceRight = page.coreRect.x + (right - page.coreDisplayLeft) / (page.sourceWidth * page.sourceScale);
  const cropLeft = clamp((sourceLeft - page.crop.x) / page.crop.width, 0, 1);
  const cropRight = clamp((sourceRight - page.crop.x) / page.crop.width, 0, 1);
  const topRatio = clamp((top - page.documentTop) / page.displayHeight, 0, 1);
  const bottomRatio = clamp((bottom - page.documentTop) / page.displayHeight, 0, 1);
  const width = cropRight - cropLeft;
  const height = bottomRatio - topRatio;
  if (width <= 0 || height <= 0) return null;
  return {
    pageId: page.sourcePageId,
    pageIndex: page.pageIndex,
    columnIndex: page.columnIndex,
    order: 0,
    rect: {
      x: cropLeft,
      y: topRatio,
      width,
      height,
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

export function moveDocumentRect(
  original: DocumentRect,
  delta: DocumentPoint,
  bounds: DocumentRect,
): DocumentRect {
  const width = original.right - original.left;
  const height = original.bottom - original.top;
  const left = clamp(original.left + delta.x, bounds.left, bounds.right - width);
  const top = clamp(original.top + delta.y, bounds.top, bounds.bottom - height);
  return { left, top, right: left + width, bottom: top + height };
}

export function documentRectFromSlices(slices: SelectionSlice[], metrics: PageMetric[]): DocumentRect | null {
  const rects = slices.flatMap((slice) => {
    const page = metrics.find((metric) => metric.pageIndex === slice.pageIndex && metric.columnIndex === slice.columnIndex)
      ?? metrics.find((metric) => metric.pageIndex === slice.pageIndex);
    if (!page) return [];
    const sourceLeft = page.crop.x + slice.rect.x * page.crop.width;
    const sourceRight = sourceLeft + slice.rect.width * page.crop.width;
    return [{
      left: page.coreDisplayLeft + (sourceLeft - page.coreRect.x) * page.sourceWidth * page.sourceScale,
      right: page.coreDisplayLeft + (sourceRight - page.coreRect.x) * page.sourceWidth * page.sourceScale,
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
