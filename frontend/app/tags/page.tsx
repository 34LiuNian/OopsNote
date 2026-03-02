"use client";

import {
  Box,
  Button,
  Flash,
  FormControl,
  Heading,
  IconButton,
  Label,
  Select,
  Spinner,
  Text,
  TextInput,
  ActionMenu,
  ActionList,
  SegmentedControl,
  CounterLabel,
} from "@primer/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { sileo } from "sileo";
import {
  GearIcon,
  GitMergeIcon,
  KebabHorizontalIcon,
  PencilIcon,
  PlusIcon,
  SearchIcon,
  TableIcon,
  TagIcon,
  TrashIcon,
  XIcon,
} from "@primer/octicons-react";
import { createTag, deleteTag, mergeTags, searchTags, updateTag } from "../../features/tags/api";
import { TAG_DIMENSIONS, useTagDimensions } from "../../features/tags";
import type { TagDimension, TagItem } from "../../types/api";

/* ── constants ────────────────────────────────────────── */

const LABEL_VARIANTS = ["secondary", "accent", "success", "attention", "danger", "done"];

type ViewMode = "label" | "card";
type DimFilter = "all" | TagDimension;

/* ── component ────────────────────────────────────────── */

export default function TagsPage() {
  const {
    setDimensions: setDims,
    effectiveDimensions: effectiveDims,
    isLoading: isLoadingDims,
    error: dimsError,
    save: saveDims,
  } = useTagDimensions();

  /* ── data state ── */
  const [allItems, setAllItems] = useState<TagItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  /* ── search  ── */
  const [query, setQuery] = useState("");

  /* ── view mode ── */
  const [viewMode, setViewMode] = useState<ViewMode>("label");
  const [dimFilter, setDimFilter] = useState<DimFilter>("all");

  /* ── create dialog ── */
  const [showCreate, setShowCreate] = useState(false);
  const [newDim, setNewDim] = useState<TagDimension>("knowledge");
  const [newValue, setNewValue] = useState("");
  const [newAliases, setNewAliases] = useState("");

  /* ── rename dialog ── */
  const [editingTag, setEditingTag] = useState<TagItem | null>(null);
  const [editValue, setEditValue] = useState("");

  /* ── delete confirm dialog ── */
  const [deletingTag, setDeletingTag] = useState<TagItem | null>(null);

  /* ── dims config dialog ── */
  const [showDimsConfig, setShowDimsConfig] = useState(false);

  /* ── merge dialog ── */
  const [mergingTag, setMergingTag] = useState<TagItem | null>(null);
  const [mergeQuery, setMergeQuery] = useState("");
  const [mergeCandidates, setMergeCandidates] = useState<TagItem[]>([]);
  const [mergeTarget, setMergeTarget] = useState<TagItem | null>(null);
  const [merging, setMerging] = useState(false);

  /* ─────────────── data loading ─────────────── */

  const loadTags = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await searchTags({
        query: query.trim() || undefined,
        limit: 2000,
      });
      setAllItems(Array.isArray(data.items) ? data.items : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载标签失败");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    loadTags();
  }, [loadTags]);

  /* ── filtered items ── */
  const filteredItems = useMemo(() => {
    if (dimFilter === "all") return allItems;
    return allItems.filter((t) => t.dimension === dimFilter);
  }, [allItems, dimFilter]);

  const dimCounts = useMemo(() => {
    const m: Record<string, number> = { all: allItems.length };
    for (const d of TAG_DIMENSIONS) m[d.key] = 0;
    for (const t of allItems) m[t.dimension] = (m[t.dimension] || 0) + 1;
    return m;
  }, [allItems]);

  /* ─────────────── CRUD handlers ─────────────── */

  const onCreate = async () => {
    const value = newValue.trim();
    if (!value) {
      sileo.error({ title: "请输入标签内容" });
      return;
    }
    const aliases = newAliases
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      await createTag({ dimension: newDim, value, aliases });
      setNewValue("");
      setNewAliases("");
      setShowCreate(false);
      sileo.success({ title: "已创建" });
      await loadTags();
    } catch (e) {
      sileo.error({
        title: "创建标签失败",
        description: e instanceof Error ? e.message : "请稍后重试",
      });
    }
  };

  const onConfirmDelete = useCallback(async () => {
    if (!deletingTag) return;
    try {
      await deleteTag(deletingTag.id);
      sileo.success({ title: "已删除" });
      setDeletingTag(null);
      await loadTags();
    } catch (e) {
      sileo.error({
        title: "删除失败",
        description: e instanceof Error ? e.message : "请稍后重试",
      });
    }
  }, [deletingTag, loadTags]);

  const onSaveRename = useCallback(async () => {
    if (!editingTag) return;
    const trimmed = editValue.trim();
    if (!trimmed) {
      sileo.error({ title: "标签内容不能为空" });
      return;
    }
    if (trimmed === editingTag.value) {
      setEditingTag(null);
      return;
    }
    try {
      await updateTag(editingTag.id, { value: trimmed });
      sileo.success({ title: "已更新" });
      setEditingTag(null);
      await loadTags();
    } catch (e) {
      sileo.error({
        title: "更新失败",
        description: e instanceof Error ? e.message : "请稍后重试",
      });
    }
  }, [editingTag, editValue, loadTags]);

  const onSaveDims = async () => {
    try {
      await saveDims();
      sileo.success({ title: "已保存配置" });
      setShowDimsConfig(false);
    } catch (e) {
      sileo.error({
        title: "保存配置失败",
        description: e instanceof Error ? e.message : "请稍后重试",
      });
    }
  };

  /* ── merge handlers ── */
  const openMerge = useCallback((tag: TagItem) => {
    setMergingTag(tag);
    setMergeQuery("");
    setMergeTarget(null);
    setMergeCandidates([]);
  }, []);

  // Search candidates when mergeQuery or mergingTag changes
  useEffect(() => {
    if (!mergingTag) return;
    let cancelled = false;
    const doSearch = async () => {
      try {
        const data = await searchTags({
          dimension: mergingTag.dimension,
          query: mergeQuery.trim() || undefined,
          limit: 50,
        });
        if (!cancelled) {
          setMergeCandidates(
            (data.items || []).filter((t) => t.id !== mergingTag.id)
          );
        }
      } catch {
        // ignore
      }
    };
    const timer = setTimeout(doSearch, 150);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [mergingTag, mergeQuery]);

  const onConfirmMerge = useCallback(async () => {
    if (!mergingTag || !mergeTarget) return;
    setMerging(true);
    try {
      const res = await mergeTags(mergingTag.id, mergeTarget.id);
      sileo.success({
        title: "合并完成",
        description: `已更新 ${res.tasks_modified} 个任务，${res.fields_modified} 处引用`,
      });
      setMergingTag(null);
      setMergeTarget(null);
      await loadTags();
    } catch (e) {
      sileo.error({
        title: "合并失败",
        description: e instanceof Error ? e.message : "请稍后重试",
      });
    } finally {
      setMerging(false);
    }
  }, [mergingTag, mergeTarget, loadTags]);

  /* ─────────────── render helpers ─────────────── */

  const getDimLabel = useCallback(
    (dim: string) => effectiveDims[dim]?.label || TAG_DIMENSIONS.find((d) => d.key === dim)?.fallbackLabel || dim,
    [effectiveDims]
  );
  const getDimVariant = useCallback(
    (dim: string) => (effectiveDims[dim]?.label_variant || "secondary") as any,
    [effectiveDims]
  );

  /* ─────────────── Main render ─────────────── */

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {/* ══════ Page Header ══════ */}
      <Box className="oops-section-header" sx={{ border: "none !important", mb: 0, pb: 2 }}>
        <TagIcon size={20} />
        <Box sx={{ flex: 1 }}>
          <Text className="oops-section-subtitle">Tags</Text>
          <Heading as="h2" className="oops-section-title" sx={{ m: 0 }}>
            标签管理
          </Heading>
        </Box>
        <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}>
          <IconButton
            aria-label="维度配置"
            icon={GearIcon}
            variant="invisible"
            onClick={() => setShowDimsConfig(true)}
          />
          <Button leadingVisual={PlusIcon} variant="primary" onClick={() => setShowCreate(true)}>
            新增标签
          </Button>
        </Box>
      </Box>

      {/* ══════ Error banners ══════ */}
      {dimsError && <Flash variant="danger">{dimsError}</Flash>}
      {error && <Flash variant="danger">{error}</Flash>}

      {/* ══════ Toolbar: search + dim filter + view switch ══════ */}
      <Box
        className="oops-card"
        sx={{
          p: 3,
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 3,
        }}
      >
        {/* Search */}
        <Box sx={{ flex: "1 1 240px", maxWidth: 360 }}>
          <TextInput
            leadingVisual={SearchIcon}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索标签…"
            trailingAction={
              query ? (
                <TextInput.Action
                  icon={XIcon}
                  aria-label="清除搜索"
                  onClick={() => setQuery("")}
                />
              ) : undefined
            }
            block
          />
        </Box>

        {/* Dimension filter */}
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", flex: "1 1 auto" }}>
          {[{ key: "all" as const, label: "全部" }, ...TAG_DIMENSIONS.map((d) => ({ key: d.key as DimFilter, label: getDimLabel(d.key) }))].map(
            (f) => (
              <Button
                key={f.key}
                size="small"
                variant={dimFilter === f.key ? "primary" : "invisible"}
                onClick={() => setDimFilter(f.key)}
                sx={{ fontWeight: dimFilter === f.key ? 600 : 400 }}
              >
                {f.label}
                <CounterLabel sx={{ ml: 1 }}>{dimCounts[f.key] ?? 0}</CounterLabel>
              </Button>
            )
          )}
        </Box>

        {/* View toggle + stats */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, ml: "auto" }}>
          <Text sx={{ color: "fg.muted", fontSize: 1, whiteSpace: "nowrap" }}>
            {loading ? <Spinner size="small" /> : `${filteredItems.length} 个标签`}
          </Text>
          <SegmentedControl aria-label="视图" size="small" onChange={(idx) => setViewMode(idx === 0 ? "label" : "card")}>
            <SegmentedControl.Button selected={viewMode === "label"} aria-label="标签视图" leadingIcon={TagIcon}>
              标签
            </SegmentedControl.Button>
            <SegmentedControl.Button selected={viewMode === "card"} aria-label="卡片视图" leadingIcon={TableIcon}>
              卡片
            </SegmentedControl.Button>
          </SegmentedControl>
        </Box>
      </Box>

      {/* ══════ Tag list area ══════ */}
      <Box className="oops-card" sx={{ p: 3 }}>
        {filteredItems.length === 0 ? (
          <Box className="oops-empty-state">
            <TagIcon size={32} />
            <Text sx={{ fontSize: 2 }}>{query ? "没有找到匹配的标签" : "暂无标签"}</Text>
            <Text sx={{ fontSize: 1 }}>
              {query ? "换个关键词试试" : "点击右上角「新增标签」开始创建"}
            </Text>
          </Box>
        ) : dimFilter === "all" ? (
          /* grouped by dimension */
          <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {TAG_DIMENSIONS.map((dim) => {
              const items = filteredItems.filter((t) => t.dimension === dim.key);
              if (items.length === 0) return null;
              return (
                <DimGroup
                  key={dim.key}
                  dimKey={dim.key}
                  label={getDimLabel(dim.key)}
                  variant={getDimVariant(dim.key)}
                  items={items}
                  viewMode={viewMode}
                  getDimLabel={getDimLabel}
                  getDimVariant={getDimVariant}
                  onDelete={setDeletingTag}
                  onRename={(t) => { setEditingTag(t); setEditValue(t.value); }}
                  onMerge={openMerge}
                />
              );
            })}
          </Box>
        ) : (
          /* flat list for single dimension */
          viewMode === "label" ? (
            <LabelView
              items={filteredItems}
              variant={getDimVariant(dimFilter)}
              onDelete={setDeletingTag}
              onRename={(t) => { setEditingTag(t); setEditValue(t.value); }}
              onMerge={openMerge}
            />
          ) : (
            <CardView
              items={filteredItems}
              getDimLabel={getDimLabel}
              getDimVariant={getDimVariant}
              onDelete={setDeletingTag}
              onRename={(t) => { setEditingTag(t); setEditValue(t.value); }}
              onMerge={openMerge}
            />
          )
        )}
      </Box>

      {/* ══════ Create Dialog ══════ */}
      {showCreate && (
        <DialogOverlay onClose={() => setShowCreate(false)}>
          <Heading as="h3" sx={{ fontSize: 3, mb: 3, display: "flex", alignItems: "center", gap: 2 }}>
            <PlusIcon size={20} /> 新增标签
          </Heading>
          <FormControl sx={{ mb: 3 }}>
            <FormControl.Label>维度</FormControl.Label>
            <Select value={newDim} onChange={(e) => setNewDim(e.target.value as TagDimension)} block>
              {TAG_DIMENSIONS.map((d) => (
                <Select.Option key={d.key} value={d.key}>
                  {getDimLabel(d.key)}
                </Select.Option>
              ))}
            </Select>
          </FormControl>
          <FormControl sx={{ mb: 3 }}>
            <FormControl.Label>标签内容</FormControl.Label>
            <TextInput
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onCreate()}
              placeholder="例如：数学/函数/单调性"
              autoFocus
              block
            />
          </FormControl>
          <FormControl sx={{ mb: 3 }}>
            <FormControl.Label>别名（可选，逗号分隔）</FormControl.Label>
            <TextInput
              value={newAliases}
              onChange={(e) => setNewAliases(e.target.value)}
              placeholder="同义词1, 同义词2"
              block
            />
          </FormControl>
          <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
            <Button onClick={() => setShowCreate(false)}>取消</Button>
            <Button variant="primary" onClick={onCreate}>创建</Button>
          </Box>
        </DialogOverlay>
      )}

      {/* ══════ Rename Dialog ══════ */}
      {editingTag && (
        <DialogOverlay onClose={() => setEditingTag(null)}>
          <Heading as="h3" sx={{ fontSize: 3, mb: 3, display: "flex", alignItems: "center", gap: 2 }}>
            <PencilIcon size={20} /> 重命名标签
          </Heading>
          <Box sx={{ mb: 3 }}>
            <Label variant={getDimVariant(editingTag.dimension)} sx={{ mr: 2 }}>
              {getDimLabel(editingTag.dimension)}
            </Label>
            <Text sx={{ color: "fg.muted", fontSize: 1 }}>{editingTag.value}</Text>
          </Box>
          <FormControl>
            <FormControl.Label>新名称</FormControl.Label>
            <TextInput
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSaveRename();
                else if (e.key === "Escape") setEditingTag(null);
              }}
              autoFocus
              block
            />
          </FormControl>
          <Box sx={{ mt: 4, display: "flex", gap: 2, justifyContent: "flex-end" }}>
            <Button onClick={() => setEditingTag(null)}>取消</Button>
            <Button variant="primary" onClick={onSaveRename}>保存</Button>
          </Box>
        </DialogOverlay>
      )}

      {/* ══════ Delete Confirm Dialog ══════ */}
      {deletingTag && (
        <DialogOverlay onClose={() => setDeletingTag(null)} narrow>
          <Heading as="h3" sx={{ fontSize: 3, mb: 3, color: "danger.fg" }}>
            删除标签
          </Heading>
          <Text sx={{ display: "block", mb: 3, lineHeight: 1.6 }}>
            确定要删除标签 <Label variant={getDimVariant(deletingTag.dimension)}>{deletingTag.value}</Label> 吗？
            {(deletingTag.ref_count ?? 0) > 0 && (
              <Text sx={{ color: "attention.fg", display: "block", mt: 2, fontSize: 1 }}>
                ⚠ 该标签被 {deletingTag.ref_count} 个题目引用，删除后不会自动从题目中移除。
              </Text>
            )}
          </Text>
          <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
            <Button onClick={() => setDeletingTag(null)}>取消</Button>
            <Button variant="danger" onClick={onConfirmDelete}>删除</Button>
          </Box>
        </DialogOverlay>
      )}

      {/* ══════ Merge Dialog ══════ */}
      {mergingTag && (
        <DialogOverlay onClose={() => setMergingTag(null)} wide>
          <Heading as="h3" sx={{ fontSize: 3, mb: 2, display: "flex", alignItems: "center", gap: 2 }}>
            <GitMergeIcon size={20} /> 合并标签
          </Heading>
          <Text sx={{ color: "fg.muted", fontSize: 1, mb: 3, display: "block" }}>
            将 <Label variant={getDimVariant(mergingTag.dimension)}>{mergingTag.value}</Label> 合并到另一个标签。
            所有引用会被替换，原标签将被删除并成为目标标签的别名。
          </Text>

          {/* 搜索目标 */}
          <FormControl sx={{ mb: 3 }}>
            <FormControl.Label>搜索目标标签（{getDimLabel(mergingTag.dimension)}）</FormControl.Label>
            <TextInput
              leadingVisual={SearchIcon}
              value={mergeQuery}
              onChange={(e) => { setMergeQuery(e.target.value); setMergeTarget(null); }}
              placeholder="输入关键词搜索同维度标签…"
              autoFocus
              block
            />
          </FormControl>

          {/* candidates list */}
          <Box
            sx={{
              maxHeight: 220,
              overflowY: "auto",
              border: "1px solid",
              borderColor: "border.default",
              borderRadius: "var(--oops-radius-sm)",
              mb: 3,
            }}
          >
            {mergeCandidates.length === 0 ? (
              <Box sx={{ p: 3, textAlign: "center", color: "fg.muted", fontSize: 1 }}>
                没有可合并的标签
              </Box>
            ) : (
              mergeCandidates.map((c) => (
                <Box
                  key={c.id}
                  onClick={() => setMergeTarget(c)}
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 2,
                    px: 3,
                    py: 2,
                    cursor: "pointer",
                    bg: mergeTarget?.id === c.id ? "accent.subtle" : "transparent",
                    borderBottom: "1px solid",
                    borderColor: "border.muted",
                    "&:last-child": { borderBottom: "none" },
                    "&:hover": { bg: mergeTarget?.id === c.id ? "accent.subtle" : "canvas.subtle" },
                    transition: "background var(--oops-transition-fast)",
                  }}
                >
                  <Box
                    sx={{
                      width: 16,
                      height: 16,
                      borderRadius: "50%",
                      border: "2px solid",
                      borderColor: mergeTarget?.id === c.id ? "accent.fg" : "border.default",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    {mergeTarget?.id === c.id && (
                      <Box sx={{ width: 8, height: 8, borderRadius: "50%", bg: "accent.fg" }} />
                    )}
                  </Box>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Text sx={{ fontWeight: 500, fontSize: 1 }}>{c.value}</Text>
                    {((c.ref_count ?? 0) > 0 || (c.aliases && c.aliases.length > 0)) && (
                      <Text sx={{ fontSize: 0, color: "fg.muted", ml: 1 }}>
                        {(c.ref_count ?? 0) > 0 ? `引用 ${c.ref_count}` : ""}
                        {(c.ref_count ?? 0) > 0 && c.aliases && c.aliases.length > 0 ? " · " : ""}
                        {c.aliases && c.aliases.length > 0 ? `别名 ${c.aliases.length}` : ""}
                      </Text>
                    )}
                  </Box>
                </Box>
              ))
            )}
          </Box>

          {/* 合并预览 */}
          {mergeTarget && (
            <Box
              sx={{
                p: 3,
                mb: 3,
                bg: "canvas.subtle",
                borderRadius: "var(--oops-radius-sm)",
                border: "1px solid",
                borderColor: "border.default",
              }}
            >
              <Text sx={{ fontSize: 1, fontWeight: 600, mb: 2, display: "block" }}>合并预览</Text>
              <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                <Label variant={getDimVariant(mergingTag.dimension)} sx={{ textDecoration: "line-through", opacity: 0.6 }}>
                  {mergingTag.value}
                </Label>
                <Text sx={{ color: "fg.muted", fontSize: 1 }}>→</Text>
                <Label variant={getDimVariant(mergeTarget.dimension)}>
                  {mergeTarget.value}
                </Label>
              </Box>
              <Text sx={{ color: "fg.muted", fontSize: 0, mt: 2, display: "block" }}>
                「{mergingTag.value}」的 {mergingTag.ref_count ?? 0} 处引用将替换为「{mergeTarget.value}」，原标签删除并成为别名。
              </Text>
            </Box>
          )}

          <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
            <Button onClick={() => setMergingTag(null)}>取消</Button>
            <Button
              variant="primary"
              onClick={onConfirmMerge}
              disabled={!mergeTarget || merging}
            >
              {merging ? <><Spinner size="small" sx={{ mr: 1 }} />合并中…</> : "确认合并"}
            </Button>
          </Box>
        </DialogOverlay>
      )}

      {/* ══════ Dims Config Dialog ══════ */}
      {showDimsConfig && (
        <DialogOverlay onClose={() => setShowDimsConfig(false)} wide>
          <Heading as="h3" sx={{ fontSize: 3, mb: 2, display: "flex", alignItems: "center", gap: 2 }}>
            <GearIcon size={20} /> 维度颜色配置
          </Heading>
          <Text sx={{ color: "fg.muted", fontSize: 1, mb: 3, display: "block" }}>
            配置每个标签维度的显示名称和颜色样式。
          </Text>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "120px 1fr 180px 80px",
              gap: 2,
              alignItems: "center",
              mb: 3,
            }}
          >
            <Text sx={{ fontWeight: "bold", fontSize: 1 }}>维度</Text>
            <Text sx={{ fontWeight: "bold", fontSize: 1 }}>显示名称</Text>
            <Text sx={{ fontWeight: "bold", fontSize: 1 }}>颜色</Text>
            <Text sx={{ fontWeight: "bold", fontSize: 1 }}>预览</Text>

            {TAG_DIMENSIONS.map((d) => (
              <Box key={d.key} sx={{ display: "contents" }}>
                <Text sx={{ fontSize: 1, color: "fg.muted" }}>{d.key}</Text>
                <TextInput
                  size="small"
                  value={effectiveDims[d.key]?.label || d.fallbackLabel}
                  onChange={(e) => {
                    setDims((prev) => ({
                      ...prev,
                      [d.key]: {
                        label: e.target.value,
                        label_variant: prev[d.key]?.label_variant || "secondary",
                      },
                    }));
                  }}
                  block
                />
                <Select
                  value={effectiveDims[d.key]?.label_variant || "secondary"}
                  onChange={(e) => {
                    setDims((prev) => ({
                      ...prev,
                      [d.key]: {
                        label: prev[d.key]?.label || d.fallbackLabel,
                        label_variant: e.target.value,
                      },
                    }));
                  }}
                  block
                >
                  {LABEL_VARIANTS.map((v) => (
                    <Select.Option key={v} value={v}>{v}</Select.Option>
                  ))}
                </Select>
                <Box sx={{ display: "flex", justifyContent: "center" }}>
                  <Label variant={getDimVariant(d.key)}>
                    {effectiveDims[d.key]?.label || d.fallbackLabel}
                  </Label>
                </Box>
              </Box>
            ))}
          </Box>
          <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
            <Button onClick={() => setShowDimsConfig(false)}>取消</Button>
            <Button variant="primary" onClick={onSaveDims} disabled={isLoadingDims}>
              {isLoadingDims ? <><Spinner size="small" sx={{ mr: 1 }} />保存中…</> : "保存配置"}
            </Button>
          </Box>
        </DialogOverlay>
      )}
    </Box>
  );
}

/* ═══════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════ */

/* ── Dialog Overlay ── */
function DialogOverlay({
  children,
  onClose,
  narrow,
  wide,
}: {
  children: React.ReactNode;
  onClose: () => void;
  narrow?: boolean;
  wide?: boolean;
}) {
  return (
    <Box
      sx={{
        position: "fixed",
        inset: 0,
        bg: "overlay.backdrop",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        animation: "fadeIn 0.15s ease-out",
      }}
      onClick={onClose}
    >
      <Box
        className="oops-card-elevated"
        sx={{
          bg: "canvas.default",
          borderRadius: "var(--oops-radius-md)",
          p: 4,
          width: "100%",
          maxWidth: narrow ? 380 : wide ? 560 : 440,
          boxShadow: "var(--oops-shadow-float)",
          animation: "slideUp 0.2s ease-out",
        }}
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
      >
        {children}
      </Box>
    </Box>
  );
}

/* ── Dimension Group (for "all" filter) ── */
function DimGroup({
  dimKey,
  label,
  variant,
  items,
  viewMode,
  getDimLabel,
  getDimVariant,
  onDelete,
  onRename,
  onMerge,
}: {
  dimKey: string;
  label: string;
  variant: any;
  items: TagItem[];
  viewMode: ViewMode;
  getDimLabel: (dim: string) => string;
  getDimVariant: (dim: string) => any;
  onDelete: (t: TagItem) => void;
  onRename: (t: TagItem) => void;
  onMerge: (t: TagItem) => void;
}) {
  return (
    <Box>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 2,
          pb: 2,
          mb: 2,
          borderBottom: "1px solid",
          borderColor: "border.muted",
        }}
      >
        <Label variant={variant} sx={{ fontSize: 0 }}>{label}</Label>
        <Text sx={{ color: "fg.muted", fontSize: 1 }}>{items.length}</Text>
      </Box>
      {viewMode === "label" ? (
        <LabelView items={items} variant={variant} onDelete={onDelete} onRename={onRename} onMerge={onMerge} />
      ) : (
        <CardView items={items} getDimLabel={getDimLabel} getDimVariant={getDimVariant} onDelete={onDelete} onRename={onRename} onMerge={onMerge} />
      )}
    </Box>
  );
}

/* ── Label View (original style) ── */
function LabelView({
  items,
  variant,
  onDelete,
  onRename,
  onMerge,
  getDimVariant,
}: {
  items: TagItem[];
  variant?: any;
  onDelete: (t: TagItem) => void;
  onRename: (t: TagItem) => void;
  onMerge: (t: TagItem) => void;
  getDimVariant?: (dim: string) => any;
}) {
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
      {items.map((t) => {
        const v = getDimVariant ? getDimVariant(t.dimension) : variant || "secondary";
        return (
          <Box
            key={t.id}
            sx={{
              display: "inline-flex",
              alignItems: "center",
              position: "relative",
              cursor: "pointer",
              "&:hover .tag-label": { opacity: 0.3 },
              "&:hover .tag-actions": { opacity: 1 },
            }}
          >
            <Label variant={v} className="tag-label" sx={{ transition: "opacity 0.15s" }}>
              {t.value}
              {(t.ref_count ?? 0) > 0 && (
                <Text sx={{ ml: 1, opacity: 0.6, fontSize: "10px" }}>×{t.ref_count}</Text>
              )}
            </Label>
            <Box
              className="tag-actions"
              sx={{
                position: "absolute",
                inset: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 1,
                opacity: 0,
                transition: "opacity 0.15s",
              }}
            >
              <IconButton
                aria-label="合并"
                icon={GitMergeIcon}
                size="small"
                variant="invisible"
                onClick={(e: React.MouseEvent) => { e.stopPropagation(); onMerge(t); }}
                sx={{ color: "fg.muted" }}
              />
              <IconButton
                aria-label="重命名"
                icon={PencilIcon}
                size="small"
                variant="invisible"
                onClick={(e: React.MouseEvent) => { e.stopPropagation(); onRename(t); }}
                sx={{ color: "fg.muted" }}
              />
              <IconButton
                aria-label="删除"
                icon={TrashIcon}
                size="small"
                variant="invisible"
                onClick={(e: React.MouseEvent) => { e.stopPropagation(); onDelete(t); }}
                sx={{ color: "danger.fg" }}
              />
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

/* ── Card View ── */
function CardView({
  items,
  getDimLabel,
  getDimVariant,
  onDelete,
  onRename,
  onMerge,
}: {
  items: TagItem[];
  getDimLabel?: (dim: string) => string;
  getDimVariant?: (dim: string) => any;
  onDelete: (t: TagItem) => void;
  onRename: (t: TagItem) => void;
  onMerge: (t: TagItem) => void;
}) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
        gap: 2,
      }}
    >
      {items.map((t) => (
        <Box
          key={t.id}
          className="oops-list-item"
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 2,
            p: 2,
            border: "1px solid",
            borderColor: "border.default",
            borderRadius: "var(--oops-radius-sm)",
            transition: "border-color var(--oops-transition-fast), box-shadow var(--oops-transition-fast)",
            "&:hover": {
              borderColor: "accent.muted",
              boxShadow: "var(--oops-shadow-sm)",
            },
          }}
        >
          {/* color indicator */}
          <Box
            sx={{
              width: 4,
              alignSelf: "stretch",
              borderRadius: 1,
              flexShrink: 0,
              bg: getDimVariant
                ? `${String(getDimVariant(t.dimension)).replace("secondary", "neutral")}.fg`
                : "accent.fg",
            }}
          />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Text sx={{ fontWeight: 500, fontSize: 1, display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {t.value}
            </Text>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: "2px" }}>
              {getDimLabel && (
                <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                  {getDimLabel(t.dimension)}
                </Text>
              )}
              {(t.ref_count ?? 0) > 0 && (
                <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                  · 引用 {t.ref_count}
                </Text>
              )}
              {t.aliases && t.aliases.length > 0 && (
                <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                  · 别名 {t.aliases.length}
                </Text>
              )}
            </Box>
          </Box>
          <ActionMenu>
            <ActionMenu.Anchor>
              <IconButton aria-label="操作" icon={KebabHorizontalIcon} variant="invisible" size="small" />
            </ActionMenu.Anchor>
            <ActionMenu.Overlay>
              <ActionList>
                <ActionList.Item onSelect={() => onRename(t)}>
                  <ActionList.LeadingVisual><PencilIcon /></ActionList.LeadingVisual>
                  重命名
                </ActionList.Item>
                <ActionList.Item onSelect={() => onMerge(t)}>
                  <ActionList.LeadingVisual><GitMergeIcon /></ActionList.LeadingVisual>
                  合并到…
                </ActionList.Item>
                <ActionList.Divider />
                <ActionList.Item variant="danger" onSelect={() => onDelete(t)}>
                  <ActionList.LeadingVisual><TrashIcon /></ActionList.LeadingVisual>
                  删除
                </ActionList.Item>
              </ActionList>
            </ActionMenu.Overlay>
          </ActionMenu>
        </Box>
      ))}
    </Box>
  );
}
