"use client";

import { memo, useRef, useEffect } from "react";
import { Box, Text, Spinner } from "@primer/react";
import type { TagDimensionStyle } from "../../types/api";

type SuggestionItem =
  | { type: "existing"; id: string; value: string; ref_count?: number }
  | { type: "create"; id: string; value: string; label: string };

type TagSuggestionListProps = {
  suggestions: SuggestionItem[];
  loading?: boolean;
  highlightIndex: number;
  onSelect: (value: string) => void;
  variant?: string;
};

export const TagSuggestionList = memo(function TagSuggestionList({
  suggestions,
  loading = false,
  highlightIndex,
  onSelect,
  variant = "secondary",
}: TagSuggestionListProps) {
  const listRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to highlightIndex
  useEffect(() => {
    const container = listRef.current;
    if (!container) return;
    const el = container.querySelector(
      `[data-suggestion-index="${highlightIndex}"]`
    ) as HTMLElement | null;
    if (!el) return;
    try {
      el.scrollIntoView({ block: "nearest" });
    } catch {
      // ignore
    }
  }, [highlightIndex]);

  if (loading) {
    return (
      <Box
        sx={{
          position: "absolute",
          top: "100%",
          left: 0,
          right: 0,
          mt: 1,
          p: 2,
          bg: "canvas.overlay",
          border: "1px solid",
          borderColor: "border.default",
          borderRadius: 2,
          boxShadow: "shadow.large",
          zIndex: 100,
          textAlign: "center",
        }}
      >
        <Spinner size="small" />
      </Box>
    );
  }

  if (suggestions.length === 0) {
    return null;
  }

  return (
    <Box
      ref={listRef}
      sx={{
        position: "absolute",
        top: "100%",
        left: 0,
        right: 0,
        mt: 1,
        p: 2,
        bg: "canvas.overlay",
        border: "1px solid",
        borderColor: "border.default",
        borderRadius: 2,
        boxShadow: "shadow.large",
        zIndex: 100,
        maxHeight: "240px",
        overflowY: "auto",
      }}
    >
      {suggestions.map((item, idx) => (
        <Box
          key={item.id}
          data-suggestion-index={idx}
          onClick={() => onSelect(item.value)}
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            px: 2,
            py: 1,
            borderRadius: 1,
            cursor: "pointer",
            bg: idx === highlightIndex ? "canvas.subtle" : "transparent",
            ":hover": {
              bg: "canvas.subtle",
            },
          }}
        >
          <Text sx={{ fontSize: 1, color: item.type === "create" ? "accent.fg" : "fg.default" }}>
            {item.type === "create" ? item.label : item.value}
          </Text>
          {item.type === "existing" && item.ref_count !== undefined && (
            <Text sx={{ fontSize: 0, color: "fg.muted" }}>
              {item.ref_count}
            </Text>
          )}
        </Box>
      ))}
    </Box>
  );
});
