"use client";

import { memo } from "react";
import { Box, Text } from "@primer/react";
import { XIcon } from "@primer/octicons-react";
import type { TagDimensionStyle } from "../../types/api";

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
      onClick={onRemove}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        bg: "transparent",
        border: "none",
        cursor: "pointer",
        color: "fg.default",
        gap: 1,
        px: 2,
        py: 1,
        borderRadius: 2,
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: variant === "primary" ? "accent.fg" : "border.default",
        ":hover": {
          bg: "canvas.subtle",
        },
      }}
    >
      <Text sx={{ fontSize: 1, lineHeight: "20px" }}>{label}</Text>
      {onRemove && (
        <Box sx={{ display: "flex", alignItems: "center" }}>
          <XIcon size={14} />
        </Box>
      )}
    </Box>
  );
});
