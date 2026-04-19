"use client";

import { useEffect, useState } from "react";
import { Box, Button, Flash, IconButton, Label, Spinner, Text, TextInput } from "@primer/react";
import { PencilIcon, TrashIcon } from "@primer/octicons-react";
import type { TagItem } from "@/types/api";

type TagsResultListProps = {
  loading: boolean;
  isLoadingDims: boolean;
  error: string;
  pagedItems: TagItem[];
  totalCount: number;
  safePage: number;
  pageCount: number;
  dimFilter: string;
  activeScope: string;
  activeDimensionLabel: string;
  getDimLabel: (dim: string) => string;
  getDimVariant: (dim: string) => any;
  getKnowledgeContext: (item: TagItem) => string;
  onPrevPage: () => void;
  onNextPage: () => void;
  onRename: (item: TagItem, nextValue: string) => Promise<void> | void;
  onDelete: (item: TagItem) => Promise<void> | void;
};

export function TagsResultList({
  loading,
  isLoadingDims,
  error,
  pagedItems,
  totalCount,
  safePage,
  pageCount,
  dimFilter,
  activeScope,
  activeDimensionLabel,
  getDimLabel,
  getDimVariant,
  getKnowledgeContext,
  onPrevPage,
  onNextPage,
  onRename,
  onDelete,
}: TagsResultListProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  useEffect(() => {
    if (!editingId) return;
    if (!pagedItems.some((item) => item.id === editingId)) {
      setEditingId(null);
      setEditingValue("");
    }
  }, [editingId, pagedItems]);

  useEffect(() => {
    if (!deleteConfirmId) return;
    if (!pagedItems.some((item) => item.id === deleteConfirmId)) {
      setDeleteConfirmId(null);
    }
  }, [deleteConfirmId, pagedItems]);

  const startRename = (item: TagItem) => {
    setDeleteConfirmId(null);
    setEditingId(item.id);
    setEditingValue(item.value);
  };

  const cancelRename = () => {
    setEditingId(null);
    setEditingValue("");
  };

  const submitRename = async (item: TagItem) => {
    const next = editingValue.trim();
    if (!next || next === item.value) {
      cancelRename();
      return;
    }

    setPendingId(item.id);
    try {
      await onRename(item, next);
      cancelRename();
    } finally {
      setPendingId((current) => (current === item.id ? null : current));
    }
  };

  const requestDelete = async (item: TagItem) => {
    if (deleteConfirmId !== item.id) {
      setDeleteConfirmId(item.id);
      return;
    }

    setPendingId(item.id);
    try {
      await onDelete(item);
      setDeleteConfirmId(null);
    } finally {
      setPendingId((current) => (current === item.id ? null : current));
    }
  };

  if (loading || isLoadingDims) {
    return (
      <Box sx={{ py: 6, display: "flex", justifyContent: "center" }}>
        <Spinner size="large" />
      </Box>
    );
  }

  if (error) {
    return <Flash variant="danger">{error}</Flash>;
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <Box>
          <Text sx={{ fontWeight: 600, fontSize: 2 }}>结果列表</Text>
          <Text sx={{ color: "fg.muted", fontSize: 1, mt: 1 }}>
            正在查看 {activeScope} 下的 {activeDimensionLabel}
          </Text>
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>
            共 {totalCount} 条，当前第 {safePage} / {pageCount} 页
          </Text>
          <Button size="small" disabled={safePage <= 1} onClick={onPrevPage}>
            上一页
          </Button>
          <Button size="small" disabled={safePage >= pageCount} onClick={onNextPage}>
            下一页
          </Button>
        </Box>
      </Box>

      {pagedItems.length === 0 ? (
        <Box className="oops-empty-state">
          <Text as="p" sx={{ fontWeight: 600, fontSize: 2 }}>
            没有找到匹配的标签
          </Text>
          <Text as="p" sx={{ fontSize: 1 }}>
            可以换个关键词，或者调整左侧目录和维度。
          </Text>
        </Box>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", borderTop: "1px solid", borderColor: "border.muted" }}>
          {pagedItems.map((item, index) => {
            const shouldShowDimLabel = dimFilter === "all" || item.dimension !== "knowledge";
            const knowledgeContext = getKnowledgeContext(item);
            const aliases = Array.isArray(item.aliases) ? item.aliases.filter(Boolean) : [];

            return (
              <Box
                key={item.id}
                className="oops-list-item"
                sx={{
                  display: "grid",
                  gridTemplateColumns: ["1fr", "minmax(0, 1fr) auto"],
                  gap: 2,
                  alignItems: "start",
                  py: 2,
                  borderBottom: "1px solid",
                  borderColor: index < pagedItems.length - 1 ? "border.muted" : "transparent",
                }}
              >
                <Box sx={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                    {shouldShowDimLabel ? (
                      <Label variant={getDimVariant(item.dimension)}>{getDimLabel(item.dimension)}</Label>
                    ) : null}
                    {editingId === item.id ? (
                      <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap", minWidth: 0 }}>
                        <TextInput
                          value={editingValue}
                          onChange={(e) => setEditingValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              void submitRename(item);
                            }
                            if (e.key === "Escape") {
                              e.preventDefault();
                              cancelRename();
                            }
                          }}
                          sx={{ minWidth: 200 }}
                        />
                        <Button size="small" variant="primary" disabled={pendingId === item.id} onClick={() => void submitRename(item)}>
                          保存
                        </Button>
                        <Button size="small" onClick={cancelRename} disabled={pendingId === item.id}>
                          取消
                        </Button>
                      </Box>
                    ) : (
                      <Text sx={{ fontWeight: 600, fontSize: 2, wordBreak: "break-word" }}>{item.value}</Text>
                    )}
                  </Box>

                  <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                    <Text sx={{ color: "fg.muted", fontSize: 1 }}>引用 {item.ref_count || 0}</Text>
                    {item.subject ? <Text sx={{ color: "fg.muted", fontSize: 1 }}>{toPlainSubject(item.subject)}</Text> : null}
                  </Box>

                  {knowledgeContext ? (
                    <Text sx={{ color: "fg.muted", fontSize: 1 }}>归属：{knowledgeContext}</Text>
                  ) : null}

                  {aliases.length > 0 ? (
                    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                      {aliases.slice(0, 4).map((alias) => (
                        <Label key={alias} variant="secondary">
                          {alias}
                        </Label>
                      ))}
                    </Box>
                  ) : null}
                </Box>

                <Box sx={{ display: "flex", alignItems: "center", gap: 1, justifyContent: ["flex-start", "flex-end"] }}>
                  <IconButton
                    aria-label="重命名"
                    icon={PencilIcon}
                    size="small"
                    disabled={pendingId === item.id}
                    onClick={() => startRename(item)}
                  />
                  <IconButton
                    aria-label="删除"
                    icon={TrashIcon}
                    size="small"
                    variant={deleteConfirmId === item.id ? "danger" : "default"}
                    disabled={pendingId === item.id}
                    onClick={() => {
                      void requestDelete(item);
                    }}
                  />
                </Box>

                {deleteConfirmId === item.id ? (
                  <Box sx={{ gridColumn: ["1", "1 / -1"] }}>
                    <Text sx={{ color: "danger.fg", fontSize: 1 }}>再次点击删除按钮以确认删除该标签。</Text>
                  </Box>
                ) : null}
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

function toPlainSubject(subject: string) {
  return subject;
}
