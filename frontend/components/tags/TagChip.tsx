"use client";

import { memo } from "react";
import { Box } from "@/components/ui/primitives";
import { XIcon } from "@/components/ui/icons";

type TagChipProps = {
  label: string;
  dimension: string;
  variant?: string;
  onRemove?: () => void;
};

export const TagChip = memo(function TagChip({ label, dimension, variant = "secondary", onRemove }: TagChipProps) {
  return (
    <Box
      as="button"
      type="button"
      className="tag-picker__token"
      data-dimension={dimension}
      data-variant={variant}
      aria-label={onRemove ? `移除标签 ${label}` : label}
      onClick={(event) => {
        event.stopPropagation();
        onRemove?.();
      }}
    >
      <span>{label}</span>
      {onRemove ? <XIcon size={12} aria-hidden="true" /> : null}
    </Box>
  );
});
