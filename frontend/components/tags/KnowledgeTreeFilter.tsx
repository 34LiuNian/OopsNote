"use client";

import { Box, Button, IconButton, Label, Spinner, Text } from "@/components/ui/primitives";
import { ChevronDownIcon, ChevronRightIcon } from "@/components/ui/icons";
import sxStyles from "./KnowledgeTreeFilter.sx.module.css";

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
    <Box className={sxStyles.sx1}>
      <span>{title}</span>
      <Label
        size="small"
        className={sxStyles.sx2}
      >
        {count}
      </Label>
    </Box>
  );

  return (
    <Box className={sxStyles.sx3}>
      <Box className={sxStyles.sx4}>
        <Box>
          <Text className={sxStyles.sx5}>知识点目录</Text>
          <Text className={sxStyles.sx6}>先选目录，再看右边对应的标签</Text>
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

      <Box className={sxStyles.sx7}>
        {chapters.map((chapter) => {
          const isChapterSelected = chapterFilter === chapter && !knowledgeFilter;
          const isChapterExpanded = expandedChapters[chapter] ?? (chapterFilter === chapter);
          const knowledgeCount = Object.keys(tree[chapter] || {}).length;

          return (
            <Box key={chapter} className={sxStyles.sx8}>
              <Box className={sxStyles.sx9}>
                <IconButton
                  size="small"
                  icon={isChapterExpanded ? ChevronDownIcon : ChevronRightIcon}
                  onClick={() => onToggleChapterExpand(chapter, chapterFilter === chapter)}
                  aria-label={isChapterExpanded ? "收起章节" : "展开章节"}
                />
                <Button
                  block
                  size="small"
                  variant={isChapterSelected ? "primary" : "default"}
                  onClick={() => onPickChapter(chapter)}
                  className={sxStyles.sx10}
                >
                  {renderTitleWithCount(chapter, knowledgeCount)}
                </Button>
              </Box>

              {isChapterExpanded ? (
                <Box className={sxStyles.sx11}>
                  {getKnowledgeByChapter(chapter).map((knowledge) => (
                    <Button
                      key={`${chapter}:${knowledge}`}
                      block
                      size="small"
                      variant={
                        chapterFilter === chapter && knowledgeFilter === knowledge ? "primary" : "default"
                      }
                      onClick={() => onPickKnowledge(chapter, knowledge)}
                      className={sxStyles.sx12}
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
