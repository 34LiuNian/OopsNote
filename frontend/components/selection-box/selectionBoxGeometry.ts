export type SelectionPoint = { x: number; y: number };
export type SelectionRect = { x: number; y: number; width: number; height: number };
export type SelectionResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";
export type SelectionMinSize = number | SelectionPoint;

export function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function clampPoint(point: SelectionPoint): SelectionPoint {
  return { x: clamp(point.x, 0, 1), y: clamp(point.y, 0, 1) };
}

function minSizeParts(minSize: SelectionMinSize): SelectionPoint {
  return typeof minSize === "number" ? { x: minSize, y: minSize } : minSize;
}

export function rectFromSelectionPoints(start: SelectionPoint, end: SelectionPoint, minSize: SelectionMinSize): SelectionRect {
  const minimum = minSizeParts(minSize);
  const width = Math.max(minimum.x, Math.abs(end.x - start.x));
  const height = Math.max(minimum.y, Math.abs(end.y - start.y));
  const x = clamp(end.x < start.x ? start.x - width : start.x, 0, 1 - width);
  const y = clamp(end.y < start.y ? start.y - height : start.y, 0, 1 - height);
  return { x, y, width, height };
}

export function moveSelectionRect(rect: SelectionRect, delta: SelectionPoint): SelectionRect {
  return {
    ...rect,
    x: clamp(rect.x + delta.x, 0, 1 - rect.width),
    y: clamp(rect.y + delta.y, 0, 1 - rect.height),
  };
}

export function resizeSelectionRect(rect: SelectionRect, handle: SelectionResizeHandle, point: SelectionPoint, minSize: SelectionMinSize): SelectionRect {
  const minimum = minSizeParts(minSize);
  const right = rect.x + rect.width;
  const bottom = rect.y + rect.height;
  const x = handle.includes("w") ? clamp(point.x, 0, right - minimum.x) : rect.x;
  const nextRight = handle.includes("e") ? clamp(point.x, rect.x + minimum.x, 1) : right;
  const y = handle.includes("n") ? clamp(point.y, 0, bottom - minimum.y) : rect.y;
  const nextBottom = handle.includes("s") ? clamp(point.y, rect.y + minimum.y, 1) : bottom;
  return { x, y, width: nextRight - x, height: nextBottom - y };
}
