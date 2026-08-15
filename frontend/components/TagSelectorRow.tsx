"use client";

import { Box, Text } from "@/components/ui/primitives";
import { TagPicker } from "./TagPicker";
import type { TagDimensionStyle } from "@/types/api";
import sxStyles from "./TagSelectorRow.sx.module.css";

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
return (
    <Box className={sxStyles.sx1}>
      <Box>
        <TagPicker
          title="来源"
          dimension="meta"
          value={sourceValue}
          onChange={onSourceChange}
          styles={styles}
          placeholder={placeholders?.source || "搜索或添加"}
        />
      </Box>

      <Box>
        <TagPicker
          title="知识体系"
          dimension="knowledge"
          value={knowledgeValue}
          onChange={onKnowledgeChange}
          styles={styles}
          placeholder={placeholders?.knowledge || "搜索或添加"}
        />
      </Box>

      <Box>
        <TagPicker
          title="错题归因"
          dimension="error"
          value={errorValue}
          onChange={onErrorChange}
          styles={styles}
          placeholder={placeholders?.error || "搜索或添加"}
        />
      </Box>

      <Box>
        <TagPicker
          title="自定义标签"
          dimension="custom"
          value={customValue}
          onChange={onCustomChange}
          styles={styles}
          placeholder={placeholders?.custom || "输入后回车"}
          enableRemoteSearch={false}
        />
      </Box>
    </Box>
  );
}
