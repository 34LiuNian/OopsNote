"use client";

import { useState } from "react";
import { Box, Button, IconButton, Label, Spinner, Text } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { RenameDialog } from "@/components/ui/RenameDialog";
import { PencilIcon, TrashIcon } from "@/components/ui/icons";
import { confirmAction } from "@/lib/confirm";
import type { TagItem } from "@/types/api";
import sxStyles from "./TagsResultList.sx.module.css";

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
  const [pendingId, setPendingId] = useState<string | null>(null);

  const editingItem = editingId ? pagedItems.find((item) => item.id === editingId) ?? null : null;

  const startRename = (item: TagItem) => {
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

  const performDelete = async (item: TagItem) => {
    setPendingId(item.id);
    try {
      await onDelete(item);
    } finally {
      setPendingId((current) => (current === item.id ? null : current));
    }
  };

  const requestDelete = (item: TagItem) => {
    confirmAction({
      title: "删除标签",
      message: `删除“${item.value}”？引用该标签的题目不会被删除。`,
      confirmLabel: "删除",
      destructive: true,
      onConfirm: () => performDelete(item),
    });
  };

  if (loading || isLoadingDims) {
    return (
      <Box className={sxStyles.sx1}>
        <Spinner size="large" />
      </Box>
    );
  }

  if (error) {
    return <ErrorBanner message={error} />;
  }

  return (
    <Box className={sxStyles.sx2}>
      <RenameDialog
        opened={editingItem !== null}
        title="重命名标签"
        label="标签名称"
        value={editingValue}
        onChange={setEditingValue}
        onCancel={cancelRename}
        onConfirm={() => editingItem ? submitRename(editingItem) : undefined}
        loading={editingItem ? pendingId === editingItem.id : false}
      />
      <Box
        className={sxStyles.sx3}
      >
        <Box>
          <Text className={sxStyles.sx4}>结果列表</Text>
          <Text className={sxStyles.sx5}>
            正在查看 {activeScope} 下的 {activeDimensionLabel}
          </Text>
        </Box>

        <Box className={sxStyles.sx6}>
          <Text className={sxStyles.sx7}>
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
          <Text as="p" className={sxStyles.sx8}>
            没有找到匹配的标签
          </Text>
          <Text as="p" className={sxStyles.sx9}>
            可以换个关键词，或者调整左侧目录和维度。
          </Text>
        </Box>
      ) : (
        <Box className={sxStyles.sx10}>
          {pagedItems.map((item, index) => {
            const shouldShowDimLabel = dimFilter === "all" || item.dimension !== "knowledge";
            const knowledgeContext = getKnowledgeContext(item);
            const aliases = Array.isArray(item.aliases) ? item.aliases.filter(Boolean) : [];

            return (
              <Box
                key={item.id}
                className={["oops-list-item", sxStyles.resultItem].join(" ")}
                data-last={index === pagedItems.length - 1 ? "true" : undefined}
              >
                <Box className={sxStyles.sx11}>
                  <Box className={sxStyles.sx12}>
                    {shouldShowDimLabel ? (
                      <Label variant={getDimVariant(item.dimension)}>{getDimLabel(item.dimension)}</Label>
                    ) : null}
                    <Text className={sxStyles.sx13}>{item.value}</Text>
                  </Box>

                  <Box className={sxStyles.sx14}>
                    <Text className={sxStyles.sx15}>引用 {item.ref_count || 0}</Text>
                    {item.subject ? <Text className={sxStyles.sx16}>{toPlainSubject(item.subject)}</Text> : null}
                  </Box>

                  {knowledgeContext ? (
                    <Text className={sxStyles.sx17}>归属：{knowledgeContext}</Text>
                  ) : null}

                  {aliases.length > 0 ? (
                    <Box className={sxStyles.sx18}>
                      {aliases.slice(0, 4).map((alias) => (
                        <Label key={alias} variant="secondary">
                          {alias}
                        </Label>
                      ))}
                    </Box>
                  ) : null}
                </Box>

                <Box className={sxStyles.sx19}>
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
                    variant="default"
                    disabled={pendingId === item.id}
                    onClick={() => requestDelete(item)}
                  />
                </Box>
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
