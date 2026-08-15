"use client";

import {
  Box,
  Button,
  FormControl,
  IconButton,
  Select,
  Text,
  TextInput,
} from "@/components/ui/primitives";
import { SidebarCollapseIcon } from "@/components/ui/icons";
import { SUBJECT_OPTIONS } from "@/config/subjects";
import type { TagDimensionStyle } from "@/types/api";
import { TagSelectorRow } from "@/components/TagSelectorRow";
import sxStyles from "./LibraryFilterPanel.sx.module.css";

const LIBRARY_SUBJECT_OPTIONS = [
  { value: "", label: "全部学科" },
  ...SUBJECT_OPTIONS,
];

export function LibraryFilterPanel({
  subject,
  onSubjectChange,
  dateAfter,
  onDateAfterChange,
  dateBefore,
  onDateBeforeChange,
  sourceValue,
  onSourceChange,
  knowledgeValue,
  onKnowledgeChange,
  errorValue,
  onErrorChange,
  customValue,
  onCustomChange,
  styles,
  activeCount,
  onClearAll,
  onClose,
}: {
  subject: string;
  onSubjectChange: (value: string) => void;
  dateAfter: string;
  onDateAfterChange: (value: string) => void;
  dateBefore: string;
  onDateBeforeChange: (value: string) => void;
  sourceValue: string[];
  onSourceChange: (value: string[]) => void;
  knowledgeValue: string[];
  onKnowledgeChange: (value: string[]) => void;
  errorValue: string[];
  onErrorChange: (value: string[]) => void;
  customValue: string[];
  onCustomChange: (value: string[]) => void;
  styles?: Record<string, TagDimensionStyle>;
  activeCount: number;
  onClearAll: () => void;
  onClose: () => void;
}) {
  return (
    <Box className="library-filter-panel">
      <Box className="oops-secondary-sidebar__header">
        <Box className={sxStyles.sx1}>
          <Text as="span">题库筛选</Text>
          {activeCount > 0 ? (
            <Box className="oops-badge oops-badge-muted">{activeCount}</Box>
          ) : null}
        </Box>
        <IconButton type="button" icon={SidebarCollapseIcon} onClick={onClose} aria-label="收起题库筛选" />
      </Box>

      <Box className="library-filter-panel__body">
        <FormControl>
          <FormControl.Label>学科</FormControl.Label>
          <Select value={subject} onValueChange={onSubjectChange} block>
            {LIBRARY_SUBJECT_OPTIONS.map((option) => (
              <Select.Option key={option.value || "all"} value={option.value}>
                {option.label}
              </Select.Option>
            ))}
          </Select>
        </FormControl>

        <FormControl>
          <FormControl.Label>日期范围</FormControl.Label>
          <Box className={sxStyles.sx2}>
            <TextInput
              type="date"
              value={dateAfter}
              onChange={(event) => onDateAfterChange(event.target.value)}
              aria-label="起始日期"
            />
            <TextInput
              type="date"
              value={dateBefore}
              onChange={(event) => onDateBeforeChange(event.target.value)}
              aria-label="结束日期"
            />
          </Box>
        </FormControl>

        <Box className="library-filter-panel__tags">
          <TagSelectorRow
            sourceValue={sourceValue}
            onSourceChange={onSourceChange}
            knowledgeValue={knowledgeValue}
            onKnowledgeChange={onKnowledgeChange}
            errorValue={errorValue}
            onErrorChange={onErrorChange}
            customValue={customValue}
            onCustomChange={onCustomChange}
            styles={styles}
            placeholders={{
              source: "搜索来源",
              knowledge: "搜索知识点",
              error: "搜索错题归因",
              custom: "输入标签后回车",
            }}
          />
        </Box>

        <Button
          size="small"
          variant="invisible"
          onClick={onClearAll}
          disabled={activeCount === 0}
          block
        >
          清空全部筛选
        </Button>
      </Box>
    </Box>
  );
}
