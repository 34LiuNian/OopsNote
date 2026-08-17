"use client";

import { useCallback, useRef, useState } from "react";
import type { NormalizedRect } from "@/types/api";
import { SelectionBox, rectFromSelectionPoints } from "@/components/selection-box";
type InteractionMode = "move" | "redraw";

export function NormalizedRectEditor({
  value,
  verticalGuides = 1,
  minSize = 0.05,
  interaction = "move",
  onChange,
  onTooSmall,
}: {
  value: NormalizedRect;
  verticalGuides?: number;
  minSize?: number;
  interaction?: InteractionMode;
  onChange: (value: NormalizedRect) => void;
  onTooSmall?: () => void;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [drawing, setDrawing] = useState<{
    pointerId: number;
    x: number;
    y: number;
    original: NormalizedRect;
  } | null>(null);

  const point = useCallback((clientX: number, clientY: number) => {
    const bounds = rootRef.current?.getBoundingClientRect();
    if (!bounds || bounds.width <= 0 || bounds.height <= 0) return { x: 0, y: 0 };
    return {
      x: Math.max(0, Math.min(1, (clientX - bounds.left) / bounds.width)),
      y: Math.max(0, Math.min(1, (clientY - bounds.top) / bounds.height)),
    };
  }, []);

  const rectFromPoints = useCallback((startX: number, startY: number, endX: number, endY: number): NormalizedRect => {
    return rectFromSelectionPoints({ x: startX, y: startY }, { x: endX, y: endY }, minSize);
  }, [minSize]);

  return (
    <div
      ref={rootRef}
      className={`normalized-rect-editor is-${interaction}`}
      data-testid="normalized-rect-editor"
      onPointerDown={(event) => {
        const target = event.target as HTMLElement;
        const canStartDrawing = event.target === event.currentTarget
          || (interaction === "redraw" && target.classList.contains("normalized-rect-editor__selection"));
        if (event.button !== 0 || !canStartDrawing) return;
        const start = point(event.clientX, event.clientY);
        setDrawing({ pointerId: event.pointerId, ...start, original: value });
        event.currentTarget.setPointerCapture(event.pointerId);
        onChange(rectFromPoints(start.x, start.y, start.x, start.y));
      }}
      onPointerMove={(event) => {
        if (!drawing || event.pointerId !== drawing.pointerId) return;
        const current = point(event.clientX, event.clientY);
        onChange(rectFromPoints(drawing.x, drawing.y, current.x, current.y));
      }}
      onPointerUp={(event) => {
        if (drawing?.pointerId !== event.pointerId) return;
        const current = point(event.clientX, event.clientY);
        if (Math.abs(current.x - drawing.x) < minSize || Math.abs(current.y - drawing.y) < minSize) {
          onChange(drawing.original);
          onTooSmall?.();
        } else {
          onChange(rectFromPoints(drawing.x, drawing.y, current.x, current.y));
        }
        setDrawing(null);
      }}
      onPointerCancel={() => {
        if (drawing) onChange(drawing.original);
        setDrawing(null);
      }}
    >
      <SelectionBox
        value={value}
        surfaceRef={rootRef}
        minSize={minSize}
        disabled={interaction === "redraw"}
        guides={verticalGuides}
        className="normalized-rect-editor__selection"
        handleClassName="normalized-rect-editor__handle"
        onChange={onChange}
      />
    </div>
  );
}
