"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { SelectionBox, type SelectionRect } from "@/components/selection-box";
import {
  clampDocumentPoint,
  normalizeRect,
  splitSelectionAcrossPages,
} from "./batchContinuousGeometry";
import type { DocumentPoint, PageMetric, SelectionModel } from "./batchContinuousTypes";
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

  const totalHeight = metrics.at(-1)?.documentBottom ?? 1;
  const documentWidth = metrics[0]?.displayWidth ?? 1000;
  const draftRect = draft ? normalizeRect(draft.start, draft.end) : null;
  const documentRectToSelectionRect = useCallback((rect: SelectionModel["rect"]): SelectionRect => ({
    x: rect.left / documentWidth,
    y: rect.top / totalHeight,
    width: (rect.right - rect.left) / documentWidth,
    height: (rect.bottom - rect.top) / totalHeight,
  }), [documentWidth, totalHeight]);
  const selectionPointClamp = useCallback((point: { x: number; y: number }) => {
    const documentPoint = clampDocumentPoint({ x: point.x * documentWidth, y: point.y * totalHeight }, metrics);
    return { x: documentPoint.x / documentWidth, y: documentPoint.y / totalHeight };
  }, [documentWidth, metrics, totalHeight]);

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
          <SelectionBox
            key={selection.id}
            value={documentRectToSelectionRect(rect)}
            surfaceRef={rootRef}
            minSize={{ x: 8 / documentWidth, y: 8 / totalHeight }}
            disabled={selection.status !== "pending"}
            showHandles={active && selection.status === "pending"}
            compactThreshold={COMPACT_HANDLE_THRESHOLD / Math.max(documentWidth, totalHeight)}
            label={<span className="batch-selection__label">{selection.questionNo}</span>}
            className={`batch-selection is-${selection.status}${active ? " is-active" : ""}${labelInside ? " is-label-inside" : ""}${compactWidth ? " is-compact-width" : ""}${compactHeight ? " is-compact-height" : ""}`}
            handleClassName="batch-selection-handle"
            data-selection-id={selection.id}
            aria-label={`第 ${selection.questionNo} 题选区`}
            clampPoint={selectionPointClamp}
            onActivate={() => onActiveSelectionChange(selection.id)}
            onChange={(nextRect) => changeRect(selection, {
              left: nextRect.x * documentWidth,
              top: nextRect.y * totalHeight,
              right: (nextRect.x + nextRect.width) * documentWidth,
              bottom: (nextRect.y + nextRect.height) * totalHeight,
            })}
          />
        );
      })}
      {draftRect && (
        <SelectionBox
          value={documentRectToSelectionRect(draftRect)}
          surfaceRef={rootRef}
          disabled
          showHandles={false}
          className="batch-selection is-draft"
          onChange={() => undefined}
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
