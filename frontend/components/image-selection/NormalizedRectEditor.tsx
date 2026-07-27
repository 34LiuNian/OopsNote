"use client";

import { useCallback, useRef, useState } from "react";
import type { NormalizedRect } from "@/types/api";

type ResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";
type InteractionMode = "move" | "redraw";

const HANDLES: ResizeHandle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

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
      x: clamp((clientX - bounds.left) / bounds.width, 0, 1),
      y: clamp((clientY - bounds.top) / bounds.height, 0, 1),
    };
  }, []);

  const startResize = useCallback((event: React.PointerEvent, handle: ResizeHandle) => {
    event.preventDefault();
    event.stopPropagation();
    const original = value;
    const pointerId = event.pointerId;
    const move = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      const nextPoint = point(moveEvent.clientX, moveEvent.clientY);
      const right = original.x + original.width;
      const bottom = original.y + original.height;
      const left = handle.includes("w") ? clamp(nextPoint.x, 0, right - minSize) : original.x;
      const nextRight = handle.includes("e") ? clamp(nextPoint.x, original.x + minSize, 1) : right;
      const top = handle.includes("n") ? clamp(nextPoint.y, 0, bottom - minSize) : original.y;
      const nextBottom = handle.includes("s") ? clamp(nextPoint.y, original.y + minSize, 1) : bottom;
      onChange({ x: left, y: top, width: nextRight - left, height: nextBottom - top });
    };
    const stop = (stopEvent: PointerEvent) => {
      if (stopEvent.pointerId !== pointerId) return;
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", stop, true);
      window.removeEventListener("pointercancel", stop, true);
    };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", stop, true);
    window.addEventListener("pointercancel", stop, true);
  }, [minSize, onChange, point, value]);

  const rectFromPoints = useCallback((startX: number, startY: number, endX: number, endY: number): NormalizedRect => {
    const width = Math.max(minSize, Math.abs(endX - startX));
    const height = Math.max(minSize, Math.abs(endY - startY));
    const x = clamp(endX < startX ? startX - width : startX, 0, 1 - width);
    const y = clamp(endY < startY ? startY - height : startY, 0, 1 - height);
    return { x, y, width, height };
  }, [minSize]);

  const startMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || event.target !== event.currentTarget) return;
    event.preventDefault();
    event.stopPropagation();
    const pointerId = event.pointerId;
    const start = point(event.clientX, event.clientY);
    const original = value;
    const move = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      const current = point(moveEvent.clientX, moveEvent.clientY);
      onChange({
        ...original,
        x: clamp(original.x + current.x - start.x, 0, 1 - original.width),
        y: clamp(original.y + current.y - start.y, 0, 1 - original.height),
      });
    };
    const stop = (stopEvent: PointerEvent) => {
      if (stopEvent.pointerId !== pointerId) return;
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", stop, true);
      window.removeEventListener("pointercancel", stop, true);
    };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", stop, true);
    window.addEventListener("pointercancel", stop, true);
  }, [onChange, point, value]);

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
      <div
        className={`normalized-rect-editor__selection${value.width < 0.08 ? " is-compact-width" : ""}${value.height < 0.08 ? " is-compact-height" : ""}`}
        onPointerDown={interaction === "move" ? startMove : undefined}
        style={{ left: `${value.x * 100}%`, top: `${value.y * 100}%`, width: `${value.width * 100}%`, height: `${value.height * 100}%` }}
      >
        {Array.from({ length: Math.max(0, verticalGuides - 1) }, (_, index) => (
          <span
            key={index}
            className="normalized-rect-editor__guide"
            style={{ left: `${(index + 1) / verticalGuides * 100}%` }}
            aria-hidden="true"
          />
        ))}
        {HANDLES.map((handle) => (
          <span key={handle} className={`normalized-rect-editor__handle is-${handle}`} onPointerDown={(event) => startResize(event, handle)} />
        ))}
      </div>
    </div>
  );
}
