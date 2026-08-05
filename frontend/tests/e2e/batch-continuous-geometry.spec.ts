import { expect, test } from "@playwright/test";
import {
  buildPageMetrics,
  compareDocumentRects,
  documentRectFromSlices,
  mapCroppedRectToOriginalSource,
  resizeDocumentRect,
  splitSelectionAcrossPages,
} from "../../components/batch-continuous/batchContinuousGeometry";
import {
  selectionsToSessionSegments,
  sessionSegmentsToSelections,
} from "../../features/upload/adapters/batchSessionSelectionAdapter";

const pages = [
  { id: "a", pageIndex: 0, label: "A", sourceWidth: 600, sourceHeight: 800 },
  { id: "b", pageIndex: 1, label: "B", sourceWidth: 1200, sourceHeight: 1600 },
  { id: "c", pageIndex: 2, label: "C", sourceWidth: 600, sourceHeight: 900 },
];

test("global proportional crop creates equal-width pages with gapless document coordinates", () => {
  const metrics = buildPageMetrics(pages, { x: 0.1, y: 0.05, width: 0.8, height: 0.9 });
  expect(metrics.map((page) => page.displayWidth)).toEqual([1000, 1000, 1000]);
  expect(metrics[0].documentBottom).toBe(metrics[1].documentTop);
  expect(metrics[1].documentBottom).toBe(metrics[2].documentTop);
  expect(metrics[0].displayHeight).toBeCloseTo(metrics[1].displayHeight);
  expect(metrics[2].displayHeight).toBeGreaterThan(metrics[1].displayHeight);
});

test("two-column layout keeps the current column aligned and borrows half of its neighbor", () => {
  const metrics = buildPageMetrics([pages[0]], { x: 0, y: 0, width: 1, height: 1 }, { columnCount: 2, overlapRatio: 0.5 });
  expect(metrics).toHaveLength(2);
  expect(metrics.map((unit) => unit.columnIndex)).toEqual([0, 1]);
  expect(metrics.map((unit) => unit.coreDisplayLeft)).toEqual([250, 250]);
  expect(metrics.map((unit) => unit.coreDisplayWidth)).toEqual([500, 500]);
  expect(metrics[0].contentLeft).toBeCloseTo(250);
  expect(metrics[0].contentRight).toBeCloseTo(1000);
  expect(metrics[1].contentLeft).toBeCloseTo(0);
  expect(metrics[1].contentRight).toBeCloseTo(750);
  expect(metrics[0].viewRect).toMatchObject({ x: 0, width: 0.75 });
  expect(metrics[1].viewRect).toMatchObject({ x: 0.25, width: 0.75 });
  expect(metrics[0].documentBottom).toBe(metrics[1].documentTop);
});

test("middle columns show both half-neighbors while edge columns leave the missing side empty", () => {
  const metrics = buildPageMetrics([pages[0]], { x: 0, y: 0, width: 1, height: 1 }, { columnCount: 3, overlapRatio: 0.5 });
  expect(metrics).toHaveLength(3);
  expect(metrics[0].contentLeft).toBeCloseTo(250);
  expect(metrics[0].contentRight).toBeCloseTo(1000);
  expect(metrics[1].contentLeft).toBeCloseTo(0);
  expect(metrics[1].contentRight).toBeCloseTo(1000);
  expect(metrics[2].contentLeft).toBeCloseTo(0);
  expect(metrics[2].contentRight).toBeCloseTo(750);
  expect(metrics[1].viewRect.x).toBeCloseTo(1 / 6);
  expect(metrics[1].viewRect.width).toBeCloseTo(2 / 3);
});

test("a cross-column document rectangle becomes ordered same-page parts and restores exactly", () => {
  const metrics = buildPageMetrics([pages[0]], { x: 0, y: 0, width: 1, height: 1 }, { columnCount: 2, overlapRatio: 0.5 });
  const rect = {
    left: 300,
    right: 700,
    top: metrics[0].documentBottom - 100,
    bottom: metrics[1].documentTop + 120,
  };
  const slices = splitSelectionAcrossPages(rect, metrics);
  expect(slices.map((slice) => [slice.pageIndex, slice.columnIndex, slice.order])).toEqual([[0, 0, 0], [0, 1, 1]]);
  const restored = documentRectFromSlices(slices, metrics);
  expect(restored?.left).toBeCloseTo(rect.left);
  expect(restored?.right).toBeCloseTo(rect.right);
  expect(restored?.top).toBeCloseTo(rect.top);
  expect(restored?.bottom).toBeCloseTo(rect.bottom);
});

test("cross-column session persistence keeps same-page part ownership", () => {
  const metrics = buildPageMetrics([pages[0]], { x: 0, y: 0, width: 1, height: 1 }, { columnCount: 2, overlapRatio: 0.5 });
  const rect = { left: 320, right: 680, top: metrics[0].documentBottom - 80, bottom: metrics[1].documentTop + 110 };
  const slices = splitSelectionAcrossPages(rect, metrics);
  const persisted = selectionsToSessionSegments([{
    id: "cross-column",
    start: { x: rect.left, y: rect.top },
    end: { x: rect.right, y: rect.bottom },
    rect,
    slices,
    questionNo: 1,
    status: "pending",
  }]);
  expect(persisted[0].parts.map((part) => [part.page_index, part.column_index, part.order])).toEqual([[0, 0, 0], [0, 1, 1]]);
  const restored = sessionSegmentsToSelections(persisted, metrics)[0];
  expect(restored.slices.map((slice) => slice.columnIndex)).toEqual([0, 1]);
  expect(restored.rect.left).toBeCloseTo(rect.left);
  expect(restored.rect.right).toBeCloseTo(rect.right);
  expect(restored.rect.top).toBeCloseTo(rect.top);
  expect(restored.rect.bottom).toBeCloseTo(rect.bottom);
});

test("one document rectangle splits across three pages and maps back to source", () => {
  const crop = { x: 0.1, y: 0.08, width: 0.8, height: 0.84 };
  const metrics = buildPageMetrics(pages, crop);
  const slices = splitSelectionAcrossPages({
    left: 150,
    right: 760,
    top: metrics[0].documentBottom - 100,
    bottom: metrics[2].documentTop + 120,
  }, metrics);
  expect(slices).toHaveLength(3);
  expect(slices.map((slice) => slice.order)).toEqual([0, 1, 2]);
  expect(slices[0].rect.y + slices[0].rect.height).toBeCloseTo(1);
  expect(slices[1].rect).toMatchObject({ y: 0, height: 1 });
  const source = mapCroppedRectToOriginalSource(slices[1].rect, crop);
  expect(source.x).toBeCloseTo(0.22);
  expect(source.y).toBeCloseTo(0.08);
  expect(source.height).toBeCloseTo(0.84);
});

test("page-boundary slices stay within the API normalized coordinate contract", () => {
  const crop = { x: 0.0029556575079856835, y: 0.04809750884086601, width: 0.9970443424920143, height: 0.9056727700328392 };
  const metrics = buildPageMetrics(pages, crop, { columnCount: 2, overlapRatio: 0.5 });
  const slices = splitSelectionAcrossPages({
    left: metrics[0].contentLeft,
    right: metrics[0].contentRight,
    top: metrics[0].documentTop,
    bottom: metrics[metrics.length - 1].documentBottom,
  }, metrics);

  expect(slices.length).toBe(metrics.length);
  for (const slice of slices) {
    expect(slice.rect.x).toBeGreaterThanOrEqual(0);
    expect(slice.rect.y).toBeGreaterThanOrEqual(0);
    expect(slice.rect.x + slice.rect.width).toBeLessThanOrEqual(1);
    expect(slice.rect.y + slice.rect.height).toBeLessThanOrEqual(1);
    expect(slice.rect.width).toBeGreaterThan(0);
    expect(slice.rect.height).toBeGreaterThan(0);
  }
});

test("resize changes one logical rectangle and ordering is top then left", () => {
  const original = { left: 100, top: 200, right: 500, bottom: 600 };
  const resized = resizeDocumentRect(original, "se", { x: 720, y: 880 }, { left: 0, top: 0, right: 1000, bottom: 2000 });
  expect(resized).toEqual({ left: 100, top: 200, right: 720, bottom: 880 });
  expect(compareDocumentRects(
    { left: 300, top: 100, right: 400, bottom: 200 },
    { left: 100, top: 100, right: 200, bottom: 200 },
  )).toBeGreaterThan(0);
});
