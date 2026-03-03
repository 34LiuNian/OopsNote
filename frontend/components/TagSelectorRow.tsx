"use client";

import { Box, Text } from "@primer/react";
import { TagPicker } from "./TagPicker";
import type { TagDimensionStyle } from "@/types/api";

/**
 * 统一的标签选择器行组件
 * 用于新建任务和组卷页面，保持统一的 UI 风格
 */
export function TagSelectorRow({
  sourceValue,
  onSourceChange,
  knowledgeValue,
  onKnowledgeChange,
  errorValue,
  onErrorChange,
  customValue,
  onCustomChange,
  styles,
  placeholders,
}: {
  sourceValue: string[];
  onSourceChange: (value: string[]) => void;
  knowledgeValue: string[];
  onKnowledgeChange: (value: string[]) => void;
  errorValue: string[];
  onErrorChange: (value: string[]) => void;
  customValue: string[];
  onCustomChange: (value: string[]) => void;
  styles?: Record<string, TagDimensionStyle>;
  placeholders?: {
    source?: string;
    knowledge?: string;
    error?: string;
    custom?: string;
  };
}) {
// - 容器宽度 < 1000px 时，单列显示（每项占满一行）
// - 容器宽度1000px+ 时，多列显示（每列最小宽度 500px，自动填充）
return (
    <Box sx={{ 
      display: "grid", 
      gridTemplateColumns: [
        "1fr",
        "repeat(auto-fit, minmax(min(500px, 100%), 1fr))",
      ],
      gap: 3 
    }}>
      {/* 第一行：来源 */}
      <Box>
        <TagPicker
          title="来源"
          dimension="meta"
          value={sourceValue}
          onChange={onSourceChange}
          styles={styles}
          placeholder={placeholders?.source || "输入后回车添加"}
        />
      </Box>

      {/* 第二行：知识体系 */}
      <Box>
        <TagPicker
          title="知识体系"
          dimension="knowledge"
          value={knowledgeValue}
          onChange={onKnowledgeChange}
          styles={styles}
          placeholder={placeholders?.knowledge || "Tab可补全"}
        />
      </Box>

      {/* 第三行：错题归因 */}
      <Box>
        <TagPicker
          title="错题归因"
          dimension="error"
          value={errorValue}
          onChange={onErrorChange}
          styles={styles}
          placeholder={placeholders?.error || "上下方向键可选择"}
        />
      </Box>

      {/* 第四行：自定义标签 */}
      <Box>
        <TagPicker
          title="自定义标签"
          dimension="custom"
          value={customValue}
          onChange={onCustomChange}
          styles={styles}
          placeholder={placeholders?.custom || "输入后回车添加"}
          enableRemoteSearch={false}
        />
      </Box>
    </Box>
  );
}
