"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Button, Label, Spinner, Text, TextInput } from "@primer/react";
import type { TagDimension, TagDimensionStyle, TagItem } from "../types/api";
import { createTag, searchTags } from "../features/tags/api";

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

export function TagPicker({
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
  const [highlightIndex, setHighlightIndex] = useState<number>(0);
  const lastReq = useRef(0);
  const listRef = useRef<HTMLDivElement | null>(null);

  const variant = styles?.[dimension]?.label_variant || "secondary";

  const addTag = useCallback(
    (raw: string) => {
      const s = normalizeTag(raw);
      if (!s) return;
      onChange(dedupeTags([...value, s]));
      setInput("");
      setOpen(false);
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
    if (!open) return;
    setHighlightIndex(0);
  }, [open, input, dimension]);

  useEffect(() => {
    if (!open) return;
    if (filteredSuggestions.length === 0) {
      setHighlightIndex(0);
      return;
    }
    setHighlightIndex((prev) => Math.max(0, Math.min(prev, filteredSuggestions.length - 1)));
  }, [filteredSuggestions.length, open]);

  useEffect(() => {
    if (!open) return;
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
  }, [highlightIndex, open]);

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
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Text sx={{ fontWeight: "bold" }}>{title}</Text>

      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
        {value.length === 0 ? (
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>未选择</Text>
        ) : (
          value.map((t) => (
            <Box key={`${dimension}:${t}`} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Label variant={variant as any}>{t}</Label>
              <Button size="small" onClick={() => removeTag(t)}>
                移除
              </Button>
            </Box>
          ))
        )}
      </Box>

      <Box sx={{ position: "relative", maxWidth: 560 }}>
        <TextInput
          value={input}
          placeholder={placeholder || "输入后回车添加"}
          onChange={(e) => {
            setInput(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            // delay so click suggestion still works
            setTimeout(() => setOpen(false), 120);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpen(false);
              return;
            }

            if (e.key === "ArrowDown") {
              if (!enableRemoteSearch) return;
              e.preventDefault();
              setOpen(true);
              if (filteredSuggestions.length === 0) return;
              setHighlightIndex((prev) => Math.min(prev + 1, filteredSuggestions.length - 1));
              return;
            }

            if (e.key === "ArrowUp") {
              if (!enableRemoteSearch) return;
              e.preventDefault();
              setOpen(true);
              if (filteredSuggestions.length === 0) return;
              setHighlightIndex((prev) => Math.max(prev - 1, 0));
              return;
            }

            if (e.key === "Tab") {
              if (open && filteredSuggestions.length > 0) {
                e.preventDefault();
                const picked = filteredSuggestions[
                  Math.max(0, Math.min(highlightIndex, filteredSuggestions.length - 1))
                ];
                if (picked.type === "existing") {
                  setInput(picked.value);
                }
              }
              return;
            }
            if (e.key === "Enter") {
              e.preventDefault();
              const picked = filteredSuggestions[Math.max(0, Math.min(highlightIndex, filteredSuggestions.length - 1))];

              // Remote search mode: Enter always prefers the first suggestion.
              if (enableRemoteSearch && picked) {
                if (picked.type === "create") {
                  void createAndAdd(picked.value);
                  return;
                }
                addTag(picked.value);
                return;
              }

              // Fallback: add raw input.
              addTag(input);
            }
          }}
          block
        />

        {enableRemoteSearch && open && (loading || filteredSuggestions.length > 0) ? (
          <Box
            ref={listRef}
            sx={{
              position: "absolute",
              left: 0,
              right: 0,
              mt: 1,
              border: "1px solid",
              borderColor: "border.default",
              borderRadius: 2,
              bg: "canvas.default",
              maxHeight: 220,
              overflowY: "auto",
              zIndex: 50,
            }}
          >
            {loading ? (
              <Box sx={{ p: 2, display: "flex", alignItems: "center", gap: 2 }}>
                <Spinner size="small" />
                <Text sx={{ fontSize: 1, color: "fg.muted" }}>搜索中…</Text>
              </Box>
            ) : (
              filteredSuggestions.map((s, idx) => (
                <Box
                  key={s.id}
                  as="button"
                  type="button"
                  data-suggestion-index={idx}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setHighlightIndex(idx)}
                  onClick={() => {
                    if (s.type === "create") {
                      void createAndAdd(s.value);
                      return;
                    }
                    addTag(s.value);
                  }}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    background: "transparent",
                    border: "none",
                    padding: 0,
                  }}
                >
                  <Box
                    sx={{
                      px: 2,
                      py: 2,
                      borderBottom: "1px solid",
                      borderColor: "border.default",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 2,
                      bg: idx === highlightIndex ? "canvas.subtle" : "canvas.default",
                    }}
                  >
                      <Text sx={{ fontSize: 1 }}>{s.type === "create" ? s.label : s.value}</Text>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                        {s.type === "existing" && typeof s.ref_count === "number" ? (
                          <Text sx={{ fontSize: 0, color: "fg.muted" }}>{`×${s.ref_count}`}</Text>
                        ) : null}
                        <Label variant={variant as any}>{styles?.[dimension]?.label || dimension}</Label>
                      </Box>
                  </Box>
                </Box>
              ))
            )}
          </Box>
        ) : null}
      </Box>

    </Box>
  );
}
