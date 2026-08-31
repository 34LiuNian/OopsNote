"use client";

import { useState } from "react";
import {
  Box,
  Button,
  FormControl,
  IconButton,
  Text,
  TextInput,
} from "@/components/ui/primitives";
import { ChevronDownIcon, ChevronRightIcon, SidebarCollapseIcon } from "@/components/ui/icons";
import { SUBJECT_OPTIONS } from "@/config/subjects";
import type { TagDimensionStyle } from "@/types/api";
import { TagPicker } from "@/components/TagPicker";
import { KnowledgeLeafPicker } from "@/components/knowledge-tree";
import { SubjectChipGroup } from "@/components/SubjectChipGroup";
import sxStyles from "./LibraryFilterPanel.sx.module.css";

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
  const moreActive = Boolean(dateAfter || dateBefore || sourceValue.length || customValue.length);
  const moreCount = [dateAfter || dateBefore, ...sourceValue, ...customValue].filter(Boolean).length;
  const [moreOpen, setMoreOpen] = useState(moreActive);

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

      <Box className={["library-filter-panel__body", sxStyles.body].join(" ")}>
        <Box className={sxStyles.primary}>
          <Box className={sxStyles.subjectRow}>
            <FormControl.Label>学科</FormControl.Label>
            <SubjectChipGroup
              value={subject}
              onChange={onSubjectChange}
              options={SUBJECT_OPTIONS}
              includeAll
            />
          </Box>

          <KnowledgeLeafPicker
            label="知识体系"
            subject={subject}
            value={knowledgeValue}
            onChange={onKnowledgeChange}
            emptyLabel="未按知识点筛选"
            subjectOptions={SUBJECT_OPTIONS}
            onSubjectChange={onSubjectChange}
            selectionMode="cascade"
            maxSelected={null}
          />

          <TagPicker
            title="错题归因"
            dimension="error"
            value={errorValue}
            onChange={onErrorChange}
            styles={styles}
            placeholder="搜索已有错因"
          />
        </Box>

        <Box className={sxStyles.more}>
          <Button
            size="small"
            variant="invisible"
            block
            contentAlign="start"
            leadingVisual={moreOpen ? ChevronDownIcon : ChevronRightIcon}
            aria-expanded={moreOpen}
            onClick={() => setMoreOpen((open) => !open)}
          >
            {moreActive ? `更多筛选 · ${moreCount}` : "更多筛选"}
          </Button>
          {moreOpen ? (
            <Box className={sxStyles.moreBody}>
              <TagPicker
                title="来源"
                dimension="meta"
                value={sourceValue}
                onChange={onSourceChange}
                styles={styles}
                placeholder="搜索来源"
              />
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
              <TagPicker
                title="备注标签"
                dimension="custom"
                value={customValue}
                onChange={onCustomChange}
                styles={styles}
                enableRemoteSearch={false}
                placeholder="输入后回车"
              />
            </Box>
          ) : null}
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
