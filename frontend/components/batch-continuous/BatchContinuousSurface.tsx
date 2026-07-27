"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildPageMetrics } from "./batchContinuousGeometry";
import type { ColumnLayout, ContinuousPageSource, DocumentCropRect, PageMetric, SelectionModel } from "./batchContinuousTypes";
import { BatchSelectionOverlay } from "./BatchSelectionOverlay";
import { NativeImage } from "@/components/ui/NativeImage";

type LazyPageProps = {
  page: PageMetric;
  inverted: boolean;
  hoveredBorrowMask?: string;
  imageUrl?: string;
  loadPage: (pageIndex: number) => void;
  onVisible: (pageIndex: number) => void;
};

function LazyPage({ page, inverted, hoveredBorrowMask, imageUrl, loadPage, onVisible }: LazyPageProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      loadPage(page.pageIndex);
      onVisible(page.pageIndex);
    }, { rootMargin: "120% 0px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [loadPage, onVisible, page.pageIndex]);

  const renderedSourceWidth = page.sourceWidth * page.sourceScale;
  const renderedSourceHeight = page.sourceHeight * page.sourceScale;
  const imageLeft = page.coreDisplayLeft - page.coreRect.x * renderedSourceWidth;
  const imageTop = -page.crop.y * renderedSourceHeight;
  const leftBorrowWidth = Math.max(0, page.coreDisplayLeft - page.contentLeft);
  const rightBorrowLeft = page.coreDisplayLeft + page.coreDisplayWidth;
  const rightBorrowWidth = Math.max(0, page.contentRight - rightBorrowLeft);
  const leftBorrowMaskId = `${page.id}:left`;
  const rightBorrowMaskId = `${page.id}:right`;
  return (
    <div
      ref={ref}
      className={`batch-continuous-page${page.columnCount > 1 ? " has-columns" : ""}${inverted ? " is-inverted" : ""}`}
      data-page-index={page.pageIndex}
      data-column-index={page.columnIndex}
      style={{ aspectRatio: String(page.displayWidth / page.displayHeight) }}
    >
      {imageUrl ? (
        <div
          className="batch-continuous-page__content"
          style={{ left: `${page.contentLeft / page.displayWidth * 100}%`, width: `${(page.contentRight - page.contentLeft) / page.displayWidth * 100}%` }}
        >
          <NativeImage
            src={imageUrl}
            alt={page.label}
            draggable={false}
            style={{
              width: `${renderedSourceWidth / (page.contentRight - page.contentLeft) * 100}%`,
              height: `${renderedSourceHeight / page.displayHeight * 100}%`,
              left: `${(imageLeft - page.contentLeft) / (page.contentRight - page.contentLeft) * 100}%`,
              top: `${imageTop / page.displayHeight * 100}%`,
            }}
          />
        </div>
      ) : <span className="batch-continuous-page__loading">正在载入第 {page.pageIndex + 1} 页</span>}
      {page.columnCount > 1 && page.columnIndex > 0 && leftBorrowWidth > 0 && (
        <span
          aria-hidden="true"
          className={`batch-continuous-page__borrow-mask is-left${hoveredBorrowMask === leftBorrowMaskId ? " is-hovered" : ""}`}
          style={{
            left: `${page.contentLeft / page.displayWidth * 100}%`,
            width: `${leftBorrowWidth / page.displayWidth * 100}%`,
          }}
        />
      )}
      {page.columnCount > 1 && page.columnIndex < page.columnCount - 1 && rightBorrowWidth > 0 && (
        <span
          aria-hidden="true"
          className={`batch-continuous-page__borrow-mask is-right${hoveredBorrowMask === rightBorrowMaskId ? " is-hovered" : ""}`}
          style={{
            left: `${rightBorrowLeft / page.displayWidth * 100}%`,
            width: `${rightBorrowWidth / page.displayWidth * 100}%`,
          }}
        />
      )}
      {page.columnCount > 1 && <span className="batch-continuous-page__column-label">第 {page.pageIndex + 1} 页 · 第 {page.columnIndex + 1} 栏</span>}
    </div>
  );
}

type Props = {
  pages: ContinuousPageSource[];
  crop: DocumentCropRect;
  columnLayout: ColumnLayout;
  imageUrls: Record<number, string>;
  loadPage: (pageIndex: number) => void;
  selections: SelectionModel[];
  activeSelectionId?: string;
  inverted?: boolean;
  zoom: number;
  viewportRef: React.RefObject<HTMLDivElement | null>;
  onVisiblePageChange: (pageIndex: number) => void;
  onActiveSelectionChange: (selectionId?: string) => void;
  onSelectionCreate: (selection: SelectionModel) => void;
  onSelectionChange: (selection: SelectionModel) => void;
  onTooSmall: () => void;
  selectionEnabled?: boolean;
};

export function BatchContinuousSurface({
  pages,
  crop,
  columnLayout,
  imageUrls,
  loadPage,
  selections,
  activeSelectionId,
  inverted = false,
  zoom,
  viewportRef,
  onVisiblePageChange,
  onActiveSelectionChange,
  onSelectionCreate,
  onSelectionChange,
  onTooSmall,
  selectionEnabled = true,
}: Props) {
  const metrics = useMemo(() => buildPageMetrics(pages, crop, columnLayout), [columnLayout, crop, pages]);
  const totalHeight = metrics.at(-1)?.documentBottom ?? 0;
  const [hoveredBorrowMask, setHoveredBorrowMask] = useState<string>();
  const updateBorrowMaskHover = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (columnLayout.columnCount <= 1 || !metrics.length || totalHeight <= 0) {
      setHoveredBorrowMask(undefined);
      return;
    }
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width * metrics[0].displayWidth;
    const y = (event.clientY - bounds.top) / bounds.height * totalHeight;
    const unit = metrics.find((metric) => y >= metric.documentTop && y < metric.documentBottom);
    let next: string | undefined;
    if (unit && unit.columnIndex > 0 && x >= unit.contentLeft && x < unit.coreDisplayLeft) {
      next = `${unit.id}:left`;
    } else if (unit && unit.columnIndex < unit.columnCount - 1) {
      const coreRight = unit.coreDisplayLeft + unit.coreDisplayWidth;
      if (x > coreRight && x <= unit.contentRight) next = `${unit.id}:right`;
    }
    setHoveredBorrowMask((current) => current === next ? current : next);
  }, [columnLayout.columnCount, metrics, totalHeight]);
  const overlayScaleStyle = {
    "--batch-selection-stroke": `${2 * zoom}px`,
    "--batch-selection-offset": `${zoom}px`,
    "--batch-selection-negative-stroke": `${-2 * zoom}px`,
    "--batch-selection-radius": `${5 * zoom}px`,
    "--batch-handle-stroke": `${3 * zoom}px`,
    "--batch-handle-offset": `${1.5 * zoom}px`,
    "--batch-handle-negative-offset": `${-1.5 * zoom}px`,
    "--batch-handle-hit": `${16 * zoom}px`,
    "--batch-handle-side-hit": `${44 * zoom}px`,
    "--batch-handle-length": `${36 * zoom}px`,
    "--batch-corner-hit": `${32 * zoom}px`,
    "--batch-corner-length": `${22 * zoom}px`,
    "--batch-corner-radius": `${5 * zoom}px`,
  } as React.CSSProperties;
  return (
    <div
      className={`batch-continuous-surface${columnLayout.columnCount > 1 ? " is-column-layout" : ""}${inverted ? " is-inverted" : ""}`}
      data-testid="batch-continuous-surface"
      onPointerMoveCapture={updateBorrowMaskHover}
      onPointerLeave={() => setHoveredBorrowMask(undefined)}
      style={{
        ...overlayScaleStyle,
        width: `${Math.round(820 * zoom)}px`,
        height: `${Math.round(820 * zoom * totalHeight / 1000)}px`,
      }}
    >
      <div className="batch-continuous-pages">
        {metrics.map((page) => (
          <LazyPage
            key={page.id}
            page={page}
            inverted={inverted}
            hoveredBorrowMask={hoveredBorrowMask}
            imageUrl={imageUrls[page.pageIndex]}
            loadPage={loadPage}
            onVisible={onVisiblePageChange}
          />
        ))}
      </div>
      {selectionEnabled && (
        <BatchSelectionOverlay
          metrics={metrics}
          selections={selections}
          activeSelectionId={activeSelectionId}
          viewportRef={viewportRef}
          onActiveSelectionChange={onActiveSelectionChange}
          onCreate={onSelectionCreate}
          onChange={onSelectionChange}
          onTooSmall={onTooSmall}
        />
      )}
    </div>
  );
}
