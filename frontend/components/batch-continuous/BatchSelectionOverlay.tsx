"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  clampDocumentPoint,
  moveDocumentRect,
  normalizeRect,
  resizeDocumentRect,
  splitSelectionAcrossPages,
} from "./batchContinuousGeometry";
import type { DocumentPoint, PageMetric, ResizeHandle, SelectionModel } from "./batchContinuousTypes";
import { GeometryButton } from "@/components/ui/primitives";

const HANDLES: ResizeHandle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const COMPACT_HANDLE_THRESHOLD = 64;

type Props = {
  metrics: PageMetric[];
  selections: SelectionModel[];
  activeSelectionId?: string;
  viewportRef: React.RefObject<HTMLDivElement | null>;
  onActiveSelectionChange: (selectionId?: string) => void;
  onCreate: (selection: SelectionModel) => void;
  onChange: (selection: SelectionModel) => void;
  onTooSmall: () => void;
};

export function BatchSelectionOverlay({
  metrics,
  selections,
  activeSelectionId,
  viewportRef,
  onActiveSelectionChange,
  onCreate,
  onChange,
  onTooSmall,
}: Props) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [draft, setDraft] = useState<{ pointerId: number; start: DocumentPoint; end: DocumentPoint } | null>(null);
  const [movingSelectionId, setMovingSelectionId] = useState<string>();

  const clientToDocument = useCallback((clientX: number, clientY: number) => {
    const bounds = rootRef.current?.getBoundingClientRect();
    if (!bounds || bounds.width <= 0 || bounds.height <= 0) return { x: 0, y: 0 };
    const totalHeight = metrics.at(-1)?.documentBottom ?? 0;
    return clampDocumentPoint({
      x: (clientX - bounds.left) / bounds.width * (metrics[0]?.displayWidth ?? 1000),
      y: (clientY - bounds.top) / bounds.height * totalHeight,
    }, metrics);
  }, [metrics]);

  const cleanupDraft = useCallback(() => setDraft(null), []);
  useEffect(() => {
    const cancel = (event: KeyboardEvent) => {
      if (event.key === "Escape") cleanupDraft();
    };
    const hidden = () => { if (document.hidden) cleanupDraft(); };
    window.addEventListener("keydown", cancel);
    window.addEventListener("blur", cleanupDraft);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      window.removeEventListener("keydown", cancel);
      window.removeEventListener("blur", cleanupDraft);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, [cleanupDraft]);

  const finishDraft = useCallback((pointerId: number) => {
    const current = draft;
    if (!current || current.pointerId !== pointerId) return;
    const rect = normalizeRect(current.start, current.end);
    setDraft(null);
    if (rect.right - rect.left < 8 || rect.bottom - rect.top < 8) {
      onTooSmall();
      return;
    }
    const id = crypto.randomUUID();
    onCreate({
      id,
      start: current.start,
      end: current.end,
      rect,
      slices: splitSelectionAcrossPages(rect, metrics),
      questionNo: 0,
      status: "pending",
    });
    onActiveSelectionChange(id);
  }, [draft, metrics, onActiveSelectionChange, onCreate, onTooSmall]);

  const changeRect = useCallback((selection: SelectionModel, rect: SelectionModel["rect"]) => {
    onChange({
      ...selection,
      rect,
      start: { x: rect.left, y: rect.top },
      end: { x: rect.right, y: rect.bottom },
      slices: splitSelectionAcrossPages(rect, metrics),
    });
  }, [metrics, onChange]);

  const startResize = useCallback((event: React.PointerEvent, selection: SelectionModel, handle: ResizeHandle) => {
    if (selection.status !== "pending") return;
    event.preventDefault();
    event.stopPropagation();
    onActiveSelectionChange(selection.id);
    const pointerId = event.pointerId;
    const original = selection.rect;
    const totalHeight = metrics.at(-1)?.documentBottom ?? 0;
    const move = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      const rect = resizeDocumentRect(
        original,
        handle,
        clientToDocument(moveEvent.clientX, moveEvent.clientY),
        { left: 0, top: 0, right: metrics[0]?.displayWidth ?? 1000, bottom: totalHeight },
      );
      changeRect(selection, rect);
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
  }, [changeRect, clientToDocument, metrics, onActiveSelectionChange]);

  const startMove = useCallback((event: React.PointerEvent, selection: SelectionModel) => {
    if (selection.status !== "pending") return;
    event.preventDefault();
    event.stopPropagation();
    onActiveSelectionChange(selection.id);
    setMovingSelectionId(selection.id);
    const pointerId = event.pointerId;
    const origin = clientToDocument(event.clientX, event.clientY);
    const original = selection.rect;
    const bounds = {
      left: 0,
      top: 0,
      right: metrics[0]?.displayWidth ?? 1000,
      bottom: metrics.at(-1)?.documentBottom ?? 0,
    };
    const move = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      const point = clientToDocument(moveEvent.clientX, moveEvent.clientY);
      changeRect(selection, moveDocumentRect(original, {
        x: point.x - origin.x,
        y: point.y - origin.y,
      }, bounds));
    };
    const stop = (stopEvent: PointerEvent) => {
      if (stopEvent.pointerId !== pointerId) return;
      setMovingSelectionId((current) => current === selection.id ? undefined : current);
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", stop, true);
      window.removeEventListener("pointercancel", stop, true);
    };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", stop, true);
    window.addEventListener("pointercancel", stop, true);
  }, [changeRect, clientToDocument, metrics, onActiveSelectionChange]);

  const totalHeight = metrics.at(-1)?.documentBottom ?? 1;
  const documentWidth = metrics[0]?.displayWidth ?? 1000;
  const draftRect = draft ? normalizeRect(draft.start, draft.end) : null;

  return (
    <div
      ref={rootRef}
      className="batch-selection-overlay"
      onPointerDown={(event) => {
        if (event.button !== 0 || event.target !== event.currentTarget) return;
        const start = clientToDocument(event.clientX, event.clientY);
        const unit = metrics.find((metric, index) => (
          start.y >= metric.documentTop
          && (start.y < metric.documentBottom || (index === metrics.length - 1 && start.y <= metric.documentBottom))
        ));
        if (!unit || start.x < unit.contentLeft || start.x > unit.contentRight) return;
        setDraft({ pointerId: event.pointerId, start, end: start });
        onActiveSelectionChange(undefined);
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const current = draft;
        if (!current || current.pointerId !== event.pointerId) return;
        const viewport = viewportRef.current;
        if (viewport) {
          const bounds = viewport.getBoundingClientRect();
          if (event.clientY < bounds.top + 48) viewport.scrollTop -= 18;
          else if (event.clientY > bounds.bottom - 48) viewport.scrollTop += 18;
        }
        setDraft({ ...current, end: clientToDocument(event.clientX, event.clientY) });
      }}
      onPointerUp={(event) => finishDraft(event.pointerId)}
      onPointerCancel={cleanupDraft}
    >
      {selections.map((selection) => {
        const active = activeSelectionId === selection.id;
        const rect = selection.rect;
        const compactWidth = rect.right - rect.left < COMPACT_HANDLE_THRESHOLD;
        const compactHeight = rect.bottom - rect.top < COMPACT_HANDLE_THRESHOLD;
        const labelInside = rect.top < 40;
        return (
          <GeometryButton
            type="button"
            key={selection.id}
            className={`batch-selection is-${selection.status}${active ? " is-active" : ""}${movingSelectionId === selection.id ? " is-moving" : ""}${labelInside ? " is-label-inside" : ""}${compactWidth ? " is-compact-width" : ""}${compactHeight ? " is-compact-height" : ""}`}
            data-selection-id={selection.id}
            aria-label={`第 ${selection.questionNo} 题选区`}
            onPointerDown={(event) => startMove(event, selection)}
            onClick={(event) => { event.stopPropagation(); onActiveSelectionChange(selection.id); }}
            style={{
              left: `${rect.left / documentWidth * 100}%`,
              top: `${rect.top / totalHeight * 100}%`,
              width: `${(rect.right - rect.left) / documentWidth * 100}%`,
              height: `${(rect.bottom - rect.top) / totalHeight * 100}%`,
            }}
          >
            <span className="batch-selection__label">{selection.questionNo}</span>
            {active && selection.status === "pending" && HANDLES.map((handle) => (
              <span key={handle} className={`batch-selection-handle is-${handle}`} onPointerDown={(event) => startResize(event, selection, handle)} />
            ))}
          </GeometryButton>
        );
      })}
      {draftRect && (
        <div
          className="batch-selection is-draft"
          style={{
            left: `${draftRect.left / documentWidth * 100}%`,
            top: `${draftRect.top / totalHeight * 100}%`,
            width: `${(draftRect.right - draftRect.left) / documentWidth * 100}%`,
            height: `${(draftRect.bottom - draftRect.top) / totalHeight * 100}%`,
          }}
        />
      )}
      {draft && (
        <span
          className="batch-continuous-crosshair"
          style={{ left: `${draft.end.x / documentWidth * 100}%`, top: `${draft.end.y / totalHeight * 100}%` }}
          aria-hidden="true"
        />
      )}
    </div>
  );
}
