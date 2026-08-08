"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, NativeInput, Text } from "@/components/ui/primitives";
import { TagChip } from "@/components/tags/TagChip";
import { TagSuggestionList } from "@/components/tags/TagSuggestionList";
import type { TagDimension, TagDimensionStyle, TagItem } from "@/types/api";
import { searchTags } from "@/features/tags/api";
import { notify } from "@/lib/notify";
import { sortTagItemsByQuery } from "@/features/tags/ranking";

export type { TagDimension, TagDimensionStyle };

type SuggestionItem =
  | { type: "existing"; id: string; value: string; ref_count?: number }
  | { type: "create"; id: string; value: string; label: string };

function normalizeTag(value: string) {
  return value.trim();
}

function dedupeTags(values: string[]) {
  const output: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const normalized = normalizeTag(value);
    if (!normalized) continue;
    const key = normalized.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(normalized);
  }
  return output;
}

export const TagPicker = memo(function TagPicker({
  title,
  dimension,
  value,
  onChange,
  placeholder,
  styles,
  enableRemoteSearch = true,
  maxSuggestions = 12,
}: {
  title: string;
  dimension: TagDimension;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  styles?: Record<string, TagDimensionStyle>;
  enableRemoteSearch?: boolean;
  maxSuggestions?: number;
}) {
  const [input, setInput] = useState("");
  const [suggestions, setSuggestions] = useState<TagItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const lastRequest = useRef(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const variant = styles?.[dimension]?.label_variant || "secondary";

  const addTag = useCallback((raw: string) => {
    const normalized = normalizeTag(raw);
    if (!normalized) return;
    onChange(dedupeTags([...value, normalized]));
    setInput("");
    setOpen(false);
  }, [onChange, value]);

  const removeTag = useCallback((raw: string) => {
    const key = normalizeTag(raw).toLowerCase();
    onChange(value.filter((tag) => normalizeTag(tag).toLowerCase() !== key));
  }, [onChange, value]);

  const filteredSuggestions = useMemo(() => {
    const selected = new Set(value.map((tag) => normalizeTag(tag).toLowerCase()));
    const available = suggestions.filter((suggestion) => !selected.has(normalizeTag(suggestion.value).toLowerCase()));
    const query = normalizeTag(input);
    const queryKey = query.toLowerCase();
    const hasExactMatch = query
      ? suggestions.some((suggestion) => (
          normalizeTag(suggestion.value).toLowerCase() === queryKey
          || (Array.isArray(suggestion.aliases)
            && suggestion.aliases.some((alias) => normalizeTag(String(alias)).toLowerCase() === queryKey))
        ))
      : false;

    const output: SuggestionItem[] = [];
    if (enableRemoteSearch && query && !hasExactMatch && !selected.has(queryKey)) {
      output.push({ type: "create", id: `create:${dimension}:${query}`, value: query, label: `新建“${query}”` });
    }
    for (const suggestion of sortTagItemsByQuery(available, query).slice(0, maxSuggestions)) {
      output.push({ type: "existing", id: suggestion.id, value: suggestion.value, ref_count: suggestion.ref_count });
    }
    return output;
  }, [dimension, enableRemoteSearch, input, maxSuggestions, suggestions, value]);

  useEffect(() => {
    if (!open) return;
    const query = input.trim();
    if (!enableRemoteSearch) return;
    const requestId = ++lastRequest.current;
    setLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const data = await searchTags({
          dimension,
          query: query || undefined,
          limit: Math.max(maxSuggestions, 20),
        });
        if (lastRequest.current === requestId) {
          setSuggestions(Array.isArray(data.items) ? data.items : []);
        }
      } catch (reason) {
        if (lastRequest.current === requestId) setSuggestions([]);
        notify.error({ title: "标签建议加载失败", description: reason instanceof Error ? reason.message : "无法搜索标签" });
      } finally {
        if (lastRequest.current === requestId) setLoading(false);
      }
    }, query ? 180 : 80);
    return () => window.clearTimeout(timer);
  }, [dimension, enableRemoteSearch, input, maxSuggestions, open]);

  useEffect(() => {
    if (!open) return;
    setHighlightIndex((current) => Math.max(0, Math.min(current, filteredSuggestions.length - 1)));
  }, [filteredSuggestions.length, open]);

  const chooseHighlighted = useCallback(() => {
    const selected = filteredSuggestions[Math.max(0, Math.min(highlightIndex, filteredSuggestions.length - 1))];
    addTag(selected?.value || input);
  }, [addTag, filteredSuggestions, highlightIndex, input]);

  return (
    <Box className="tag-picker" data-dimension={dimension}>
      <Text className="tag-picker__title">{title}</Text>
      <Box sx={{ position: "relative" }}>
        <Box
          className={`tag-picker__field${open ? " is-focused" : ""}`}
          onClick={() => inputRef.current?.focus()}
        >
          {value.map((tag) => (
            <TagChip
              key={`${dimension}:${tag}`}
              label={tag}
              dimension={dimension}
              variant={variant}
              onRemove={() => removeTag(tag)}
            />
          ))}
          <NativeInput
            ref={inputRef}
            className="tag-picker__input"
            aria-label={`${title}标签输入`}
            value={input}
            placeholder={placeholder || (enableRemoteSearch ? "搜索或添加" : "输入后回车")}
            onChange={(event) => {
              setInput(event.target.value);
              setOpen(true);
              setHighlightIndex(0);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => window.setTimeout(() => setOpen(false), 120)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setOpen(false);
                return;
              }
              if (event.key === "Backspace" && input === "" && value.length > 0) {
                event.preventDefault();
                removeTag(value[value.length - 1]);
                return;
              }
              if (event.key === "ArrowDown" && filteredSuggestions.length > 0) {
                event.preventDefault();
                setOpen(true);
                setHighlightIndex((current) => Math.min(current + 1, filteredSuggestions.length - 1));
                return;
              }
              if (event.key === "ArrowUp" && filteredSuggestions.length > 0) {
                event.preventDefault();
                setOpen(true);
                setHighlightIndex((current) => Math.max(current - 1, 0));
                return;
              }
              if (event.key === "Enter") {
                event.preventDefault();
                chooseHighlighted();
              }
            }}
          />
        </Box>

        {enableRemoteSearch && open && (loading || filteredSuggestions.length > 0) ? (
          <TagSuggestionList
            suggestions={filteredSuggestions}
            loading={loading}
            highlightIndex={highlightIndex}
            onHighlight={setHighlightIndex}
            onSelect={addTag}
          />
        ) : null}
      </Box>
    </Box>
  );
});
