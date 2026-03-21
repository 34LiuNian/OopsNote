"use client";

import { Box, Label, Select, TextInput } from "@primer/react";
import { SearchIcon } from "@primer/octicons-react";
import type { TagDimension } from "@/types/api";

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
}: TagsToolbarProps) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 220px"], gap: 2 }}>
        <TextInput
          leadingVisual={SearchIcon}
          placeholder="搜索标签名或别名"
          value={queryInput}
          onChange={(e) => onQueryInputChange(e.target.value)}
        />

        <Select value={dimFilter} onChange={(e) => onDimFilterChange(e.target.value as DimFilter)}>
          <Select.Option value="all">全部维度（{dimCounts.all || 0}）</Select.Option>
          {tagDimensions.map((dim) => (
            <Select.Option key={dim.key} value={dim.key}>
              {getDimLabel(dim.key)}（{dimCounts[dim.key] || 0}）
            </Select.Option>
          ))}
        </Select>
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        {activePathParts.length > 0 ? (
          activePathParts.map((part, index) => (
            <Label key={`${part}-${index}`} variant={index === activePathParts.length - 1 ? "accent" : "secondary"}>
              {part}
            </Label>
          ))
        ) : (
          <Label>全部知识点</Label>
        )}
      </Box>
    </Box>
  );
}
