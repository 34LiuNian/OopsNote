"use client";

import { memo, useState, useCallback } from "react";
import { Box, TextInput } from "@primer/react";
import { TagSuggestionList } from "./TagSuggestionList";

type SuggestionItem =
  | { type: "existing"; id: string; value: string; ref_count?: number }
  | { type: "create"; id: string; value: string; label: string };

type TagSearchInputProps = {
  value: string;
  onChange: (value: string) => void;
  onSelect: (value: string) => void;
  suggestions: SuggestionItem[];
  loading?: boolean;
  highlightIndex: number;
  onHighlightIndexChange: (index: number) => void;
  placeholder?: string;
  variant?: string;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
};

export const TagSearchInput = memo(function TagSearchInput({
  value,
  onChange,
  onSelect,
  suggestions,
  loading = false,
  highlightIndex,
  onHighlightIndexChange,
  placeholder,
  variant = "secondary",
  onKeyDown,
}: TagSearchInputProps) {
  const [isOpen, setIsOpen] = useState(false);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    onKeyDown?.(e);
    
    if (e.key === "ArrowDown") {
      e.preventDefault();
      onHighlightIndexChange(Math.min(highlightIndex + 1, suggestions.length - 1));
      setIsOpen(true);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      onHighlightIndexChange(Math.max(highlightIndex - 1, 0));
      setIsOpen(true);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (suggestions.length > 0 && highlightIndex >= 0) {
        onSelect(suggestions[highlightIndex].value);
        setIsOpen(false);
      }
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  }, [highlightIndex, suggestions, onSelect, onHighlightIndexChange, onKeyDown]);

  return (
    <Box sx={{ position: "relative", flex: 1, minWidth: 0 }}>
      <TextInput
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setIsOpen(true);
        }}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setTimeout(() => setIsOpen(false), 150)}
        onKeyDown={handleKeyDown}
        sx={{
          width: "100%",
          input: {
            border: "1px solid",
            borderColor: variant === "primary" ? "accent.fg" : "border.default",
          },
        }}
      />
      <TagSuggestionList
        suggestions={suggestions}
        loading={loading}
        highlightIndex={highlightIndex}
        onSelect={onSelect}
        variant={variant}
      />
    </Box>
  );
});
