"use client";

import { Box, Button, Flash, IconButton, Label, Spinner, Text } from "@primer/react";
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
  onRename: (item: TagItem) => void;
  onDelete: (item: TagItem) => void;
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
                    <Text sx={{ fontWeight: 600, fontSize: 2, wordBreak: "break-word" }}>{item.value}</Text>
                  </Box>

                  <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                    <Text sx={{ color: "fg.muted", fontSize: 1 }}>引用 {item.ref_count || 0}</Text>
                    {item.subject ? <Text sx={{ color: "fg.muted", fontSize: 1 }}>{toPlainSubject(item.subject)}</Text> : null}
                    {item.grade ? <Text sx={{ color: "fg.muted", fontSize: 1 }}>{item.grade}</Text> : null}
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
                  <IconButton aria-label="重命名" icon={PencilIcon} size="small" onClick={() => onRename(item)} />
                  <IconButton
                    aria-label="删除"
                    icon={TrashIcon}
                    size="small"
                    variant="danger"
                    onClick={() => onDelete(item)}
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
