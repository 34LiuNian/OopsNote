"use client";

import { useEffect, useMemo, useRef } from "react";
import { buildPageMetrics } from "./batchContinuousGeometry";
import type { ContinuousPageSource, DocumentCropRect, SelectionModel } from "./batchContinuousTypes";
import { BatchSelectionOverlay } from "./BatchSelectionOverlay";

type LazyPageProps = {
  page: ContinuousPageSource;
  crop: DocumentCropRect;
  inverted: boolean;
  imageUrl?: string;
  loadPage: (pageIndex: number) => void;
  onVisible: (pageIndex: number) => void;
};

function LazyPage({ page, crop, inverted, imageUrl, loadPage, onVisible }: LazyPageProps) {
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

  const croppedAspect = (page.sourceWidth * crop.width) / (page.sourceHeight * crop.height);
  return (
    <div
      ref={ref}
      className={`batch-continuous-page${inverted ? " is-inverted" : ""}`}
      data-page-index={page.pageIndex}
      style={{ aspectRatio: String(croppedAspect) }}
    >
      {imageUrl ? (
        <img
          src={imageUrl}
          alt={page.label}
          draggable={false}
          style={{
            width: `${100 / crop.width}%`,
            height: `${100 / crop.height}%`,
            left: `${-crop.x / crop.width * 100}%`,
            top: `${-crop.y / crop.height * 100}%`,
          }}
        />
      ) : <span className="batch-continuous-page__loading">正在载入第 {page.pageIndex + 1} 页</span>}
    </div>
  );
}

type Props = {
  pages: ContinuousPageSource[];
  crop: DocumentCropRect;
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
  const metrics = useMemo(() => buildPageMetrics(pages, crop), [crop, pages]);
  const totalHeight = metrics.at(-1)?.documentBottom ?? 0;
  return (
    <div
      className="batch-continuous-surface"
      data-testid="batch-continuous-surface"
      style={{ width: `${Math.round(820 * zoom)}px`, height: `${Math.round(820 * zoom * totalHeight / 1000)}px` }}
    >
      <div className="batch-continuous-pages">
        {pages.map((page) => (
          <LazyPage
            key={page.id}
            page={page}
            crop={crop}
            inverted={inverted}
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
