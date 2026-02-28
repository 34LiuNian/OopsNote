"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Text } from "@primer/react";
import type { TagDimension, TagDimensionStyle, TagItem } from "../types/api";
import { createTag, searchTags } from "../features/tags/api";
import { TagChip } from "./tags/TagChip";
import { TagSearchInput } from "./tags/TagSearchInput";

export type { TagDimension, TagDimensionStyle };

type SuggestionItem =
  | { type: "existing"; id: string; value: string; ref_count?: number }
  | { type: "create"; id: string; value: string; label: string };

function normalizeTag(value: string) {
  return value.trim();
}

function dedupeTags(values: string[]) {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const v of values) {
    const s = normalizeTag(v);
    if (!s) continue;
    const key = s.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
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
  const [highlightIndex, setHighlightIndex] = useState<number>(0);
  const lastReq = useRef(0);

  const variant = styles?.[dimension]?.label_variant || "secondary";

  const addTag = useCallback(
    (raw: string) => {
      const s = normalizeTag(raw);
      if (!s) return;
      onChange(dedupeTags([...value, s]));
      setInput("");
    },
    [onChange, value]
  );

  const createAndAdd = useCallback(
    async (raw: string) => {
      const s = normalizeTag(raw);
      if (!s) return;
      try {
        await createTag({ dimension, value: s, aliases: [] });
      } catch {
        // ignore; still add locally
      }
      addTag(s);
    },
    [addTag, dimension]
  );

  const removeTag = useCallback(
    (raw: string) => {
      const key = normalizeTag(raw).toLowerCase();
      onChange(value.filter((t) => normalizeTag(t).toLowerCase() !== key));
    },
    [onChange, value]
  );

  const filteredSuggestions = useMemo(() => {
    const selected = new Set(value.map((t) => normalizeTag(t).toLowerCase()));
    const list = suggestions.filter((s) => !selected.has(normalizeTag(s.value).toLowerCase()));

    const q = normalizeTag(input);
    const qKey = q.toLowerCase();
    const hasExactInSuggestions = q
      ? suggestions.some((s) => {
          if (normalizeTag(s.value).toLowerCase() === qKey) return true;
          const aliases = Array.isArray(s.aliases) ? s.aliases : [];
          return aliases.some((a) => normalizeTag(String(a)).toLowerCase() === qKey);
        })
      : false;
    const alreadySelected = q ? selected.has(qKey) : false;

    const out: SuggestionItem[] = [];
    if (enableRemoteSearch && q && !hasExactInSuggestions && !alreadySelected) {
      out.push({ type: "create", id: `create:${dimension}:${q}`, value: q, label: `新建：${q}` });
    }

    for (const s of list.slice(0, maxSuggestions)) {
      out.push({ type: "existing", id: s.id, value: s.value, ref_count: s.ref_count });
    }
    return out;
  }, [dimension, enableRemoteSearch, input, maxSuggestions, suggestions, value]);

  useEffect(() => {
    setHighlightIndex(0);
  }, [input, dimension]);

  useEffect(() => {
    const q = input.trim();
    if (!enableRemoteSearch) {
      setSuggestions([]);
      return;
    }

    // When empty, show top tags by ref_count.
    const requestId = ++lastReq.current;
    setLoading(true);

    const timer = setTimeout(async () => {
      try {
        const data = await searchTags({
          dimension,
          query: q || undefined,
          limit: Math.max(maxSuggestions, 20),
        });
        if (lastReq.current !== requestId) return;
        setSuggestions(Array.isArray(data.items) ? data.items : []);
      } catch {
        if (lastReq.current !== requestId) return;
        setSuggestions([]);
      } finally {
        if (lastReq.current === requestId) setLoading(false);
      }
    }, q ? 180 : 80);

    return () => clearTimeout(timer);
  }, [dimension, enableRemoteSearch, input, maxSuggestions]);

  return (
    <Box sx={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 2 }}>
      <Text sx={{ fontWeight: "bold", lineHeight: "28px" }}>{title}</Text>

      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, flex: 1, minWidth: 0, alignItems: "center" }}>
        {value.length === 0 ? (
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>未选择</Text>
        ) : (
          value.map((t) => (
            <TagChip
              key={`${dimension}:${t}`}
              label={t}
              dimension={dimension}
              variant={variant}
              onRemove={() => removeTag(t)}
            />
          ))
        )}
      </Box>

      <Box sx={{ maxWidth: 560, flexShrink: 0 }}>
        <TagSearchInput
          value={input}
          onChange={setInput}
          onSelect={(selected) => {
            const picked = filteredSuggestions.find(s => s.value === selected);
            if (picked?.type === "create") {
              void createAndAdd(picked.value);
            } else {
              addTag(selected);
            }
          }}
          suggestions={filteredSuggestions}
          loading={loading}
          highlightIndex={highlightIndex}
          onHighlightIndexChange={setHighlightIndex}
          placeholder={placeholder || "输入后回车添加"}
          variant={variant}
          onKeyDown={(e) => {
            if (e.key === "Backspace") {
              if (input === "" && value.length > 0) {
                e.preventDefault();
                removeTag(value[value.length - 1]);
              }
            }
          }}
        />
      </Box>
    </Box>
  );
});
