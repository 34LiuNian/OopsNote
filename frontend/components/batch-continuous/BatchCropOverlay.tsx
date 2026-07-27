"use client";

import { NormalizedCropOverlay } from "@/components/image-crop/NormalizedCropOverlay";
import type { DocumentCropRect } from "./batchContinuousTypes";

export function BatchCropOverlay({
  value,
  columnCount = 1,
  onChange,
  onTooSmall,
}: {
  value: DocumentCropRect;
  columnCount?: number;
  onChange: (value: DocumentCropRect) => void;
  onTooSmall: () => void;
}) {
  return (
    <NormalizedCropOverlay
      value={value}
      columnCount={columnCount}
      onChange={onChange}
      onTooSmall={onTooSmall}
    />
  );
}
