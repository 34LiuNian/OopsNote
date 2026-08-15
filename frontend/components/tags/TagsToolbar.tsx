"use client";

import { Box, Button, Label, Select, TextInput } from "@/components/ui/primitives";
import { SearchIcon } from "@/components/ui/icons";
import type { TagDimension } from "@/types/api";
import sxStyles from "./TagsToolbar.sx.module.css";

type DimFilter = "all" | TagDimension;

type TagsToolbarProps = {
  queryInput: string;
  onQueryInputChange: (value: string) => void;
  dimFilter: DimFilter;
  onDimFilterChange: (value: DimFilter) => void;
  dimCounts: Record<string, number>;
  getDimLabel: (dim: string) => string;
  tagDimensions: Array<{ key: TagDimension; fallbackLabel: string }>;
  activePathParts: string[];
  onClearQuery: () => void;
  onResetKnowledgeScope: () => void;
};

export function TagsToolbar({
  queryInput,
  onQueryInputChange,
  dimFilter,
  onDimFilterChange,
  dimCounts,
  getDimLabel,
  tagDimensions,
  activePathParts,
  onClearQuery,
  onResetKnowledgeScope,
}: TagsToolbarProps) {
  return (
    <Box className={sxStyles.sx1}>
      <Box className={sxStyles.sx2}>
        <TextInput
          leadingVisual={SearchIcon}
          placeholder="搜索标签名或别名，默认按引用次数排序"
          value={queryInput}
          onChange={(e) => onQueryInputChange(e.target.value)}
        />

        <Select value={dimFilter} onValueChange={(value) => onDimFilterChange(value as DimFilter)}>
          <Select.Option value="all">全部维度（{dimCounts.all || 0}）</Select.Option>
          {tagDimensions.map((dim) => (
            <Select.Option key={dim.key} value={dim.key}>
              {getDimLabel(dim.key)}（{dimCounts[dim.key] || 0}）
            </Select.Option>
          ))}
        </Select>
      </Box>

      <Box className={sxStyles.sx3}>
        {activePathParts.length > 0 ? (
          activePathParts.map((part, index) => (
            <Label key={`${part}-${index}`} variant={index === activePathParts.length - 1 ? "accent" : "secondary"}>
              {part}
            </Label>
          ))
        ) : (
          <Label>全部知识点</Label>
        )}

        {queryInput.trim() ? (
          <Button size="small" variant="invisible" onClick={onClearQuery}>
            清空搜索
          </Button>
        ) : null}

        {activePathParts.length > 0 ? (
          <Button size="small" variant="invisible" onClick={onResetKnowledgeScope}>
            返回全部知识点
          </Button>
        ) : null}
      </Box>
    </Box>
  );
}
