"use client";

import { memo, useEffect, useRef } from "react";
import { Box, Spinner, Text } from "@/components/ui/primitives";

type SuggestionItem =
  | { type: "existing"; id: string; value: string; ref_count?: number }
  | { type: "create"; id: string; value: string; label: string };

type TagSuggestionListProps = {
  suggestions: SuggestionItem[];
  loading?: boolean;
  highlightIndex: number;
  onHighlight: (index: number) => void;
  onSelect: (value: string) => void;
};

export const TagSuggestionList = memo(function TagSuggestionList({
  suggestions,
  loading = false,
  highlightIndex,
  onHighlight,
  onSelect,
}: TagSuggestionListProps) {
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(`[data-suggestion-index="${highlightIndex}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex]);

  return (
    <Box ref={listRef} className="tag-picker__suggestions" role="listbox">
      {loading ? (
        <Box className="tag-picker__loading"><Spinner size="small" /></Box>
      ) : suggestions.map((item, index) => (
        <Box
          key={item.id}
          as="button"
          type="button"
          role="option"
          aria-selected={index === highlightIndex}
          data-suggestion-index={index}
          className={`tag-picker__suggestion${index === highlightIndex ? " is-highlighted" : ""}`}
          onMouseDown={(event) => event.preventDefault()}
          onPointerEnter={() => onHighlight(index)}
          onClick={() => onSelect(item.value)}
        >
          <Text sx={{ fontSize: 1 }}>{item.type === "create" ? item.label : item.value}</Text>
          {item.type === "existing" && typeof item.ref_count === "number" ? (
            <Text sx={{ color: "fg.muted", fontSize: 0 }}>{item.ref_count}</Text>
          ) : null}
        </Box>
      ))}
    </Box>
  );
});
