"use client";

import { useCallback, useState } from "react";
import type { CSSProperties, ReactNode, RefObject } from "react";
import {
  clampPoint,
  moveSelectionRect,
  resizeSelectionRect,
  type SelectionPoint,
  type SelectionMinSize,
  type SelectionRect,
  type SelectionResizeHandle,
} from "./selectionBoxGeometry";

const HANDLES: SelectionResizeHandle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

type SelectionBoxProps = {
  value: SelectionRect;
  surfaceRef: RefObject<HTMLElement | null>;
  minSize?: SelectionMinSize;
  disabled?: boolean;
  showHandles?: boolean;
  compactThreshold?: number;
  label?: ReactNode;
  guides?: number;
  className?: string;
  handleClassName?: string;
  dataSelectionId?: string;
  ariaLabel?: string;
  clampPoint?: (point: SelectionPoint) => SelectionPoint;
  onChange: (value: SelectionRect) => void;
  onActivate?: () => void;
};

function clientPoint(surfaceRef: RefObject<HTMLElement | null>, clientX: number, clientY: number, mapPoint?: (point: SelectionPoint) => SelectionPoint) {
  const bounds = surfaceRef.current?.getBoundingClientRect();
  if (!bounds || bounds.width <= 0 || bounds.height <= 0) return { x: 0, y: 0 };
  const point = {
    x: (clientX - bounds.left) / bounds.width,
    y: (clientY - bounds.top) / bounds.height,
  };
  return mapPoint ? mapPoint(point) : clampPoint(point);
}

export function SelectionBox({
  value,
  surfaceRef,
  minSize = 0.05,
  disabled = false,
  showHandles = true,
  compactThreshold = 0.08,
  label,
  guides = 1,
  className = "",
  handleClassName = "",
  dataSelectionId,
  ariaLabel,
  clampPoint: mapPoint,
  onChange,
  onActivate,
}: SelectionBoxProps) {
  const [moving, setMoving] = useState(false);
  const startResize = useCallback((event: React.PointerEvent, handle: SelectionResizeHandle) => {
    if (disabled) return;
    event.preventDefault();
    event.stopPropagation();
    onActivate?.();
    setMoving(true);
    const pointerId = event.pointerId;
    const original = value;
    const move = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      onChange(resizeSelectionRect(original, handle, clientPoint(surfaceRef, moveEvent.clientX, moveEvent.clientY, mapPoint), minSize));
    };
    const stop = (stopEvent: PointerEvent) => {
      if (stopEvent.pointerId !== pointerId) return;
      setMoving(false);
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", stop, true);
      window.removeEventListener("pointercancel", stop, true);
    };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", stop, true);
    window.addEventListener("pointercancel", stop, true);
  }, [disabled, mapPoint, minSize, onActivate, onChange, surfaceRef, value]);

  const startMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (disabled || event.button !== 0 || event.target !== event.currentTarget) return;
    event.preventDefault();
    event.stopPropagation();
    onActivate?.();
    setMoving(true);
    const pointerId = event.pointerId;
    const start = clientPoint(surfaceRef, event.clientX, event.clientY, mapPoint);
    const original = value;
    const move = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      const current = clientPoint(surfaceRef, moveEvent.clientX, moveEvent.clientY, mapPoint);
      onChange(moveSelectionRect(original, { x: current.x - start.x, y: current.y - start.y }));
    };
    const stop = (stopEvent: PointerEvent) => {
      if (stopEvent.pointerId !== pointerId) return;
      setMoving(false);
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", stop, true);
      window.removeEventListener("pointercancel", stop, true);
    };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", stop, true);
    window.addEventListener("pointercancel", stop, true);
  }, [disabled, mapPoint, onActivate, onChange, surfaceRef, value]);

  const compactWidth = value.width < compactThreshold;
  const compactHeight = value.height < compactThreshold;
  const classes = [
    "selection-box",
    compactWidth ? "is-compact-width" : "",
    compactHeight ? "is-compact-height" : "",
    moving ? "is-moving" : "",
    className,
  ].filter(Boolean).join(" ");
  const geometryStyle = {
    "--oops-geometry-left": `${value.x * 100}%`,
    "--oops-geometry-top": `${value.y * 100}%`,
    "--oops-geometry-width": `${value.width * 100}%`,
    "--oops-geometry-height": `${value.height * 100}%`,
  } as CSSProperties;

  return (
    <div
      className={classes}
      data-selection-id={dataSelectionId}
      aria-label={ariaLabel}
      aria-disabled={disabled || undefined}
      role={ariaLabel ? "button" : undefined}
      tabIndex={ariaLabel ? 0 : undefined}
      onPointerDown={startMove}
      onClick={onActivate}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onActivate?.();
        }
      }}
      style={geometryStyle}
    >
      {label}
      {Array.from({ length: Math.max(0, guides - 1) }, (_, index) => (
        <span
          key={index}
          className="selection-box__guide"
          style={{ "--oops-geometry-guide-left": `${(index + 1) / guides * 100}%` } as CSSProperties}
          aria-hidden="true"
        />
      ))}
      {showHandles && !disabled && HANDLES.map((handle) => (
        <span
          key={handle}
          className={`selection-box__handle is-${handle} ${handleClassName}`.trim()}
          onPointerDown={(event) => startResize(event, handle)}
        />
      ))}
    </div>
  );
}
