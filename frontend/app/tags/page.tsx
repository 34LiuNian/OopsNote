"use client";

import {
  Box,
  Button,
  FormControl,
  Heading,
  Label,
  Select,
  Text,
  TextInput,
} from "@primer/react";
import { PlusIcon, TagIcon } from "@primer/octicons-react";
import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { KnowledgeTreeFilter } from "@/components/tags/KnowledgeTreeFilter";
import { TagsResultList } from "@/components/tags/TagsResultList";
import { TagsToolbar } from "@/components/tags/TagsToolbar";
import { SUBJECT_OPTIONS } from "@/config/subjects";
import { sortTagItemsByQuery } from "@/features/tags/ranking";
import { notify } from "@/lib/notify";
import type { TagDimension, TagItem } from "@/types/api";
import { createTag, deleteTag, searchTags, updateTag } from "../../features/tags/api";
import { TAG_DIMENSIONS, useTagDimensions } from "../../features/tags";

type DimFilter = "all" | TagDimension;
type ChapterTree = Record<string, Record<string, number>>;

const PAGE_SIZE = 120;

const SUBJECT_LABEL_MAP: Record<string, string> = Object.fromEntries(
  SUBJECT_OPTIONS.map((item) => [item.value, item.label])
);

function toLabel(subject: string): string {
  return SUBJECT_LABEL_MAP[subject] || subject || "未分类";
}

function chapterFromAlias(item: TagItem, alias: string): string | null {
  const normalized = String(alias || "")
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean);
  if (normalized.length < 3) return null;

  const subjectLabel = item.subject ? toLabel(item.subject) : "";
  if (subjectLabel && normalized[0] !== subjectLabel) return null;
  return normalized[1] || null;
}

function inferChapter(item: TagItem): string {
  const chapter = String(item.chapter || "").trim();
  if (chapter) return chapter;
  const aliases = Array.isArray(item.aliases) ? item.aliases : [];
  for (const alias of aliases) {
    const inferred = chapterFromAlias(item, alias);
    if (inferred) return inferred;
  }
  return "未分章节";
}

function sortText(items: Iterable<string>) {
  return Array.from(items).sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function sortChapters(items: Iterable<string>) {
  return Array.from(items).sort((a, b) => {
    if (a === "未分章节") return 1;
    if (b === "未分章节") return -1;
    return a.localeCompare(b, "zh-CN");
  });
}

function sortKnowledgePoints(items: Iterable<string>) {
  return sortText(items);
}

export default function TagsPage() {
  const { effectiveDimensions, isLoading: isLoadingDims } = useTagDimensions();

  const [items, setItems] = useState<TagItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [dimFilter, setDimFilter] = useState<DimFilter>("knowledge");

  const [chapterFilter, setChapterFilter] = useState("");
  const [knowledgeFilter, setKnowledgeFilter] = useState("");
  const [expandedChapters, setExpandedChapters] = useState<Record<string, boolean>>({});

  const [allKnowledgeItems, setAllKnowledgeItems] = useState<TagItem[]>([]);
  const [loadingKnowledgeTree, setLoadingKnowledgeTree] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [newDim, setNewDim] = useState<TagDimension>("knowledge");
  const [newValue, setNewValue] = useState("");
  const [newAliases, setNewAliases] = useState("");
  const [newSubject, setNewSubject] = useState("");
  const [newChapter, setNewChapter] = useState("");

  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(queryInput.trim()), 220);
    return () => clearTimeout(timer);
  }, [queryInput]);

  const loadKnowledgeTree = useCallback(async () => {
    setLoadingKnowledgeTree(true);
    try {
      const data = await searchTags({
        dimension: "knowledge",
        limit: 5000,
      });
      setAllKnowledgeItems(Array.isArray(data.items) ? data.items : []);
    } catch {
      setAllKnowledgeItems([]);
    } finally {
      setLoadingKnowledgeTree(false);
    }
  }, []);

  const loadTags = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const shouldUseKnowledgeFilter = dimFilter === "knowledge" || dimFilter === "all";
      const data = await searchTags({
        dimension: dimFilter === "all" ? undefined : dimFilter,
        query: query || undefined,
        chapter: shouldUseKnowledgeFilter ? chapterFilter || undefined : undefined,
        limit: 2000,
      });

      let nextItems = Array.isArray(data.items) ? data.items : [];
      if (shouldUseKnowledgeFilter && chapterFilter) {
        nextItems = nextItems.filter(
          (item) => item.dimension === "knowledge" && inferChapter(item) === chapterFilter
        );
      }
      if (shouldUseKnowledgeFilter && knowledgeFilter) {
        nextItems = nextItems.filter(
          (item) => item.dimension === "knowledge" && item.value === knowledgeFilter
        );
      }

      setItems(nextItems);
      setPage(1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载标签失败");
    } finally {
      setLoading(false);
    }
  }, [chapterFilter, dimFilter, knowledgeFilter, query]);

  useEffect(() => {
    void loadKnowledgeTree();
  }, [loadKnowledgeTree]);

  useEffect(() => {
    void loadTags();
  }, [loadTags]);

  const tree = useMemo<ChapterTree>(() => {
    const result: ChapterTree = {};
    for (const item of allKnowledgeItems) {
      const chapter = inferChapter(item);
      const knowledge = String(item.value || "").trim() || "未命名知识点";
      result[chapter] = result[chapter] || {};
      result[chapter][knowledge] = (result[chapter][knowledge] || 0) + 1;
    }
    return result;
  }, [allKnowledgeItems]);

  const chapters = useMemo(() => sortChapters(Object.keys(tree)), [tree]);

  const getKnowledgeByChapter = useCallback(
    (chapter: string) => sortKnowledgePoints(Object.keys(tree[chapter] || {})),
    [tree]
  );

  const deferredItems = useDeferredValue(items);
  const pageCount = Math.max(1, Math.ceil(deferredItems.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);

  const pagedItems = useMemo(
    () => deferredItems.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [deferredItems, safePage]
  );

  const dimCounts = useMemo(() => {
    const counts: Record<string, number> = { all: items.length };
    for (const d of TAG_DIMENSIONS) counts[d.key] = 0;
    for (const item of items) {
      const dim = (item.dimension || "knowledge") as TagDimension;
      counts[dim] = (counts[dim] || 0) + 1;
    }
    return counts;
  }, [items]);

  const totalRefs = useMemo(
    () => deferredItems.reduce((sum, item) => sum + (item.ref_count || 0), 0),
    [deferredItems]
  );

  const highFreqItems = useMemo(() => {
    if (query) return [];
    return sortTagItemsByQuery(deferredItems, "").slice(0, 10);
  }, [deferredItems, query]);

  const getDimLabel = useCallback(
    (dim: string) =>
      effectiveDimensions[dim]?.label ||
      TAG_DIMENSIONS.find((d) => d.key === dim)?.fallbackLabel ||
      dim,
    [effectiveDimensions]
  );

  const getDimVariant = useCallback(
    (dim: string) => (effectiveDimensions[dim]?.label_variant || "secondary") as any,
    [effectiveDimensions]
  );

  const getKnowledgeContext = useCallback(
    (item: TagItem) => {
      if (item.dimension !== "knowledge") return "";

      const parts: string[] = [];
      if (item.subject) parts.push(toLabel(item.subject));
      parts.push(inferChapter(item));
      return parts.join(" / ");
    },
    []
  );

  const activePathParts = useMemo(
    () => [chapterFilter, knowledgeFilter].filter(Boolean),
    [chapterFilter, knowledgeFilter]
  );

  const activeScope = activePathParts.length > 0 ? activePathParts.join(" / ") : "全部章节 / 知识点";
  const activeDimensionLabel = getDimLabel(dimFilter === "all" ? "knowledge" : dimFilter);

  const resetCreateDraft = useCallback(() => {
    setNewValue("");
    setNewAliases("");
    setNewSubject("");
    setNewChapter(chapterFilter || "");
  }, [chapterFilter]);

  const onCreate = useCallback(async () => {
    const value = newValue.trim();
    if (!value) {
      notify.error({ title: "请输入标签内容" });
      return;
    }

    try {
      const aliases = newAliases
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      await createTag({
        dimension: newDim,
        value,
        aliases,
        subject: newDim === "knowledge" ? newSubject || undefined : undefined,
        chapter: newDim === "knowledge" ? newChapter.trim() || undefined : undefined,
      });

      setShowCreate(false);
      resetCreateDraft();
      notify.success({ title: "标签已创建" });
      await Promise.all([loadTags(), loadKnowledgeTree()]);
    } catch (e) {
      notify.error({
        title: "创建失败",
        description: e instanceof Error ? e.message : "请稍后重试",
      });
    }
  }, [
    loadKnowledgeTree,
    loadTags,
    newAliases,
    newChapter,
    newDim,
    newSubject,
    newValue,
    resetCreateDraft,
  ]);

  const onRename = useCallback(
    async (item: TagItem, next: string) => {
      if (!next || next === item.value) return;

      try {
        await updateTag(item.id, { value: next });
        notify.success({ title: "标签已更新" });
        await Promise.all([loadTags(), loadKnowledgeTree()]);
      } catch (e) {
        notify.error({
          title: "更新失败",
          description: e instanceof Error ? e.message : "请稍后重试",
        });
        throw e;
      }
    },
    [loadKnowledgeTree, loadTags]
  );

  const onDelete = useCallback(
    async (item: TagItem) => {
      try {
        await deleteTag(item.id);
        notify.success({ title: "标签已删除" });
        await Promise.all([loadTags(), loadKnowledgeTree()]);
      } catch (e) {
        notify.error({
          title: "删除失败",
          description: e instanceof Error ? e.message : "请稍后重试",
        });
        throw e;
      }
    },
    [loadKnowledgeTree, loadTags]
  );

  const clearAllFilters = useCallback(() => {
    setChapterFilter("");
    setKnowledgeFilter("");
    setDimFilter("knowledge");
    setQueryInput("");
    setQuery("");
  }, []);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box className="oops-section-header" sx={{ border: "none !important", mb: 0, pb: 2 }}>
        <TagIcon size={20} />
        <Box sx={{ flex: 1 }}>
          <Text className="oops-section-subtitle">Tags</Text>
          <Heading as="h2" className="oops-section-title" sx={{ m: 0 }}>
            标签管理
          </Heading>
          <Text sx={{ color: "fg.muted", fontSize: 1, mt: 1 }}>
            左边选目录，右边看结果和操作。尽量把“当前在看什么”说清楚。
          </Text>
        </Box>
        <Button
          leadingVisual={PlusIcon}
          onClick={() => {
            setShowCreate((v) => !v);
            if (!showCreate) resetCreateDraft();
          }}
        >
          {showCreate ? "收起新建" : "新建标签"}
        </Button>
      </Box>

      <Box
        className="oops-card"
        sx={{
          p: 3,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 3,
          flexWrap: "wrap",
        }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
            <Text sx={{ fontWeight: 600 }}>当前范围</Text>
            <Label variant="accent">{activeDimensionLabel}</Label>
            <Text sx={{ color: "fg.default", fontWeight: 600, wordBreak: "break-word" }}>{activeScope}</Text>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
            <Text sx={{ color: "fg.muted", fontSize: 1 }}>
              共 {deferredItems.length} 个标签
            </Text>
            <Text sx={{ color: "fg.muted", fontSize: 1 }}>
              总引用 {totalRefs}
            </Text>
            <Text sx={{ color: "fg.muted", fontSize: 1 }}>
              章节目录 {chapters.length}
            </Text>
            {query ? <Label>{`搜索：${query}`}</Label> : null}
          </Box>
        </Box>

        <Button size="small" variant="invisible" onClick={clearAllFilters}>
          清空筛选
        </Button>
      </Box>

      {highFreqItems.length > 0 ? (
        <Box className="oops-card" sx={{ p: 3, display: "flex", flexDirection: "column", gap: 2 }}>
          <Text sx={{ fontWeight: 600 }}>高频标签快捷入口</Text>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>
            下面是当前范围里最常用的标签，点一下即可快速定位。
          </Text>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
            {highFreqItems.map((item) => (
              <Button
                key={`hot-${item.id}`}
                size="small"
                onClick={() => {
                  setQueryInput(item.value);
                  setQuery(item.value);
                }}
              >
                {item.value}
                <Text as="span" sx={{ color: "fg.muted", ml: 1, fontSize: 0 }}>
                  ×{item.ref_count || 0}
                </Text>
              </Button>
            ))}
          </Box>
        </Box>
      ) : null}

      {showCreate ? (
        <Box className="oops-card" sx={{ p: 3, display: "flex", flexDirection: "column", gap: 3 }}>
          <Box>
            <Heading as="h3" sx={{ fontSize: 2, mb: 1 }}>
              新建标签
            </Heading>
            <Text sx={{ color: "fg.muted", fontSize: 1 }}>
              如果当前已经选中了章节或知识点，新标签会自动沿用对应章节。
            </Text>
          </Box>

          <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "repeat(3, minmax(0, 1fr))"], gap: 2 }}>
            <FormControl>
              <FormControl.Label>维度</FormControl.Label>
              <Select value={newDim} onChange={(e) => setNewDim(e.target.value as TagDimension)}>
                {TAG_DIMENSIONS.map((dim) => (
                  <Select.Option key={dim.key} value={dim.key}>
                    {getDimLabel(dim.key)}
                  </Select.Option>
                ))}
              </Select>
            </FormControl>

            {newDim === "knowledge" ? (
              <>
                <FormControl>
                  <FormControl.Label>学科</FormControl.Label>
                  <Select value={newSubject} onChange={(e) => setNewSubject(e.target.value)}>
                    <Select.Option value="">未指定</Select.Option>
                    {SUBJECT_OPTIONS.map((option) => (
                      <Select.Option key={option.value} value={option.value}>
                        {option.label}
                      </Select.Option>
                    ))}
                  </Select>
                </FormControl>

                <FormControl>
                  <FormControl.Label>章节</FormControl.Label>
                  <TextInput
                    value={newChapter}
                    onChange={(e) => setNewChapter(e.target.value)}
                    placeholder="例如：全等三角形"
                  />
                </FormControl>
              </>
            ) : null}
          </Box>

          <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "2fr 1fr"], gap: 2 }}>
            <FormControl>
              <FormControl.Label>标签名称</FormControl.Label>
              <TextInput
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="输入标签内容"
              />
            </FormControl>

            <FormControl>
              <FormControl.Label>别名</FormControl.Label>
              <TextInput
                value={newAliases}
                onChange={(e) => setNewAliases(e.target.value)}
                placeholder="多个别名用英文逗号分隔"
              />
            </FormControl>
          </Box>

          <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, alignItems: "center", flexWrap: "wrap" }}>
            <Text sx={{ color: "fg.muted", fontSize: 1 }}>
              {activePathParts.length > 0 ? `将默认归入：${activeScope}` : "当前没有目录约束，适合创建通用标签。"}
            </Text>
            <Button variant="primary" onClick={onCreate}>
              创建标签
            </Button>
          </Box>
        </Box>
      ) : null}

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: ["1fr", "320px minmax(0, 1fr)"],
          gap: 3,
          alignItems: "start",
        }}
      >
        <Box className="oops-card" sx={{ p: 3 }}>
          <KnowledgeTreeFilter
            loading={loadingKnowledgeTree}
            chapters={chapters}
            tree={tree}
            chapterFilter={chapterFilter}
            knowledgeFilter={knowledgeFilter}
            expandedChapters={expandedChapters}
            getKnowledgeByChapter={getKnowledgeByChapter}
            onClearAll={() => {
              setChapterFilter("");
              setKnowledgeFilter("");
              setDimFilter("knowledge");
            }}
            onPickChapter={(chapter) => {
              setChapterFilter(chapter);
              setKnowledgeFilter("");
              setDimFilter("knowledge");
            }}
            onPickKnowledge={(chapter, knowledge) => {
              setChapterFilter(chapter);
              setKnowledgeFilter(knowledge);
              setDimFilter("knowledge");
            }}
            onToggleChapterExpand={(chapter, defaultExpanded) => {
              setExpandedChapters((prev) => ({
                ...prev,
                [chapter]: !(prev[chapter] ?? defaultExpanded),
              }));
            }}
          />
        </Box>

        <Box className="oops-card" sx={{ p: 3, display: "flex", flexDirection: "column", gap: 3 }}>
          <TagsToolbar
            queryInput={queryInput}
            onQueryInputChange={setQueryInput}
            dimFilter={dimFilter}
            onDimFilterChange={setDimFilter}
            dimCounts={dimCounts}
            getDimLabel={getDimLabel}
            tagDimensions={TAG_DIMENSIONS}
            activePathParts={activePathParts}
            onClearQuery={() => {
              setQueryInput("");
              setQuery("");
            }}
            onResetKnowledgeScope={() => {
              setChapterFilter("");
              setKnowledgeFilter("");
              setDimFilter("knowledge");
            }}
          />

          <TagsResultList
            loading={loading}
            isLoadingDims={isLoadingDims}
            error={error}
            pagedItems={pagedItems}
            totalCount={deferredItems.length}
            safePage={safePage}
            pageCount={pageCount}
            dimFilter={dimFilter}
            activeScope={activeScope}
            activeDimensionLabel={activeDimensionLabel}
            getDimLabel={getDimLabel}
            getDimVariant={getDimVariant}
            getKnowledgeContext={getKnowledgeContext}
            onPrevPage={() => setPage((p) => Math.max(1, p - 1))}
            onNextPage={() => setPage((p) => Math.min(pageCount, p + 1))}
            onRename={(item, nextValue) => {
              void onRename(item, nextValue);
            }}
            onDelete={(item) => {
              void onDelete(item);
            }}
          />
        </Box>
      </Box>
    </Box>
  );
}
