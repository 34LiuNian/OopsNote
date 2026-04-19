"use client";

import { Box, Button, Label, Spinner, Text } from "@primer/react";
import { ChevronDownIcon, ChevronRightIcon } from "@primer/octicons-react";

type ChapterTree = Record<string, Record<string, number>>;

type KnowledgeTreeFilterProps = {
  loading: boolean;
  chapters: string[];
  tree: ChapterTree;
  chapterFilter: string;
  knowledgeFilter: string;
  expandedChapters: Record<string, boolean>;
  getKnowledgeByChapter: (chapter: string) => string[];
  onClearAll: () => void;
  onPickChapter: (chapter: string) => void;
  onPickKnowledge: (chapter: string, knowledge: string) => void;
  onToggleChapterExpand: (chapter: string, defaultExpanded: boolean) => void;
};

export function KnowledgeTreeFilter({
  loading,
  chapters,
  tree,
  chapterFilter,
  knowledgeFilter,
  expandedChapters,
  getKnowledgeByChapter,
  onClearAll,
  onPickChapter,
  onPickKnowledge,
  onToggleChapterExpand,
}: KnowledgeTreeFilterProps) {
  const renderTitleWithCount = (title: string, count: number) => (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
      <span>{title}</span>
      <Label
        size="small"
        sx={{
          minWidth: 22,
          justifyContent: "center",
          borderRadius: 999,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {count}
      </Label>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Box>
          <Text sx={{ fontWeight: 600 }}>知识点目录</Text>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>先选目录，再看右边对应的标签</Text>
        </Box>
        {loading ? <Spinner size="small" /> : null}
      </Box>

      <Button
        block
        size="small"
        onClick={onClearAll}
        variant={!chapterFilter && !knowledgeFilter ? "primary" : "default"}
      >
        全部知识点
      </Button>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1, maxHeight: 640, overflowY: "auto" }}>
        {chapters.map((chapter) => {
          const isChapterSelected = chapterFilter === chapter && !knowledgeFilter;
          const isChapterExpanded = expandedChapters[chapter] ?? (chapterFilter === chapter);
          const knowledgeCount = Object.keys(tree[chapter] || {}).length;

          return (
            <Box key={chapter} sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <Box sx={{ display: "grid", gridTemplateColumns: "32px 1fr", gap: 1 }}>
                <Button
                  size="small"
                  sx={{ px: 0 }}
                  onClick={() => onToggleChapterExpand(chapter, chapterFilter === chapter)}
                  aria-label={isChapterExpanded ? "收起章节" : "展开章节"}
                >
                  {isChapterExpanded ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
                </Button>
                <Button
                  block
                  size="small"
                  variant={isChapterSelected ? "primary" : "default"}
                  onClick={() => onPickChapter(chapter)}
                  sx={{ justifyContent: "space-between" }}
                >
                  {renderTitleWithCount(chapter, knowledgeCount)}
                </Button>
              </Box>

              {isChapterExpanded ? (
                <Box sx={{ pl: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                  {getKnowledgeByChapter(chapter).map((knowledge) => (
                    <Button
                      key={`${chapter}:${knowledge}`}
                      block
                      size="small"
                      variant={
                        chapterFilter === chapter && knowledgeFilter === knowledge ? "primary" : "default"
                      }
                      onClick={() => onPickKnowledge(chapter, knowledge)}
                      sx={{ justifyContent: "space-between" }}
                    >
                      {renderTitleWithCount(knowledge, tree[chapter]?.[knowledge] || 0)}
                    </Button>
                  ))}
                </Box>
              ) : null}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
