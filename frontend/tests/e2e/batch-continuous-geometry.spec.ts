import { expect, test } from "@playwright/test";
import {
  buildPageMetrics,
  compareDocumentRects,
  mapCroppedRectToOriginalSource,
  resizeDocumentRect,
  splitSelectionAcrossPages,
} from "../../components/batch-continuous/batchContinuousGeometry";

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

test("resize changes one logical rectangle and ordering is top then left", () => {
  const original = { left: 100, top: 200, right: 500, bottom: 600 };
  const resized = resizeDocumentRect(original, "se", { x: 720, y: 880 }, { left: 0, top: 0, right: 1000, bottom: 2000 });
  expect(resized).toEqual({ left: 100, top: 200, right: 720, bottom: 880 });
  expect(compareDocumentRects(
    { left: 300, top: 100, right: 400, bottom: 200 },
    { left: 100, top: 100, right: 200, bottom: 200 },
  )).toBeGreaterThan(0);
});
