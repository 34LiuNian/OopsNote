"use client";

import { useCallback, useRef, useState } from "react";
import type { DocumentCropRect, ResizeHandle } from "./batchContinuousTypes";
import { clamp } from "./batchContinuousGeometry";

const HANDLES: ResizeHandle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

type Props = {
  value: DocumentCropRect;
  onChange: (value: DocumentCropRect) => void;
};

export function BatchCropOverlay({ value, onChange }: Props) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [drawing, setDrawing] = useState<{ pointerId: number; x: number; y: number } | null>(null);

  const point = useCallback((clientX: number, clientY: number) => {
    const bounds = rootRef.current?.getBoundingClientRect();
    if (!bounds) return { x: 0, y: 0 };
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
      const left = handle.includes("w") ? clamp(nextPoint.x, 0, right - 0.02) : original.x;
      const nextRight = handle.includes("e") ? clamp(nextPoint.x, original.x + 0.02, 1) : right;
      const top = handle.includes("n") ? clamp(nextPoint.y, 0, bottom - 0.02) : original.y;
      const nextBottom = handle.includes("s") ? clamp(nextPoint.y, original.y + 0.02, 1) : bottom;
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
  }, [onChange, point, value]);

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
      className="batch-crop-overlay"
      onPointerDown={(event) => {
        if (event.button !== 0 || event.target !== event.currentTarget) return;
        const start = point(event.clientX, event.clientY);
        setDrawing({ pointerId: event.pointerId, ...start });
        event.currentTarget.setPointerCapture(event.pointerId);
        onChange({ x: start.x, y: start.y, width: 0.001, height: 0.001 });
      }}
      onPointerMove={(event) => {
        if (!drawing || event.pointerId !== drawing.pointerId) return;
        const current = point(event.clientX, event.clientY);
        onChange({
          x: Math.min(drawing.x, current.x),
          y: Math.min(drawing.y, current.y),
          width: Math.max(0.001, Math.abs(current.x - drawing.x)),
          height: Math.max(0.001, Math.abs(current.y - drawing.y)),
        });
      }}
      onPointerUp={(event) => {
        if (drawing?.pointerId === event.pointerId) setDrawing(null);
      }}
      onPointerCancel={() => setDrawing(null)}
    >
      <div className="batch-crop-overlay__shade" aria-hidden="true" />
      <div
        className="batch-crop-overlay__rect"
        onPointerDown={startMove}
        style={{ left: `${value.x * 100}%`, top: `${value.y * 100}%`, width: `${value.width * 100}%`, height: `${value.height * 100}%` }}
      >
        {HANDLES.map((handle) => (
          <span key={handle} className={`batch-selection-handle is-${handle}`} onPointerDown={(event) => startResize(event, handle)} />
        ))}
      </div>
    </div>
  );
}
