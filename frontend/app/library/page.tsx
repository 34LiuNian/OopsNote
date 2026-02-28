"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import {
  Box,
  Heading,
  Text,
  Label,
  Select,
  TextInput,
  FormControl,
  Spinner,
} from "@primer/react";
import { sileo } from "sileo";
import { useEffect } from "react";
import { useActiveTaskList, useProblemList } from "../../features/tasks";
import { ProblemListItem } from "../../components/ProblemListItem";
import { TaskThumbnail } from "../../components/TaskThumbnail";
import { TagSelectorRow } from "../../components/TagSelectorRow";
import { ListSkeleton } from "../../components/LoadingStates";
import { useTagDimensions } from "../../features/tags";

const SUBJECT_OPTIONS = [
  { value: "", label: "全部学科" },
  { value: "math", label: "数学" },
  { value: "physics", label: "物理" },
  { value: "chemistry", label: "化学" },
];

export default function LibraryPage() {
  const [subject, setSubject] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [knowledgeFilter, setKnowledgeFilter] = useState<string[]>([]);
  const [errorFilter, setErrorFilter] = useState<string[]>([]);
  const [customFilter, setCustomFilter] = useState<string[]>([]);
  const { effectiveDimensions: tagStyles } = useTagDimensions();
  const {
    items,
    isLoading,
    error,
  } = useProblemList({ 
    subject: subject || undefined, 
    source: sourceFilter.length > 0 ? sourceFilter : undefined,
    knowledge_tag: knowledgeFilter.length > 0 ? knowledgeFilter : undefined,
    error_tag: errorFilter.length > 0 ? errorFilter : undefined,
    user_tag: customFilter.length > 0 ? customFilter : undefined,
  });
  const {
    items: activeTasks,
    activeItems: activeTaskItems,
    isLoading: isLoadingActive,
  } = useActiveTaskList({ active_only: true, subject: subject || undefined });
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});


  const toggleSelected = useCallback((key: string) => {
    setSelectedIds((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // 显示错误通知
  useEffect(() => {
    if (error) {
      sileo.error({ title: error });
    }
  }, [error]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {/* Active Tasks */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2, minHeight: 200 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Tasks</Text>
            <Heading as="h2" sx={{ fontSize: 3 }}>进行中的任务</Heading>
          </Box>
          {isLoadingActive ? (
            <Label variant="secondary">刷新中...</Label>
          ) : activeTaskItems.length > 0 ? (
            <Label variant="secondary">进行中 {activeTaskItems.length} 条</Label>
          ) : (
            <Label variant="secondary">暂无进行中任务</Label>
          )}
        </Box>

        {activeTaskItems.length === 0 ? (
          isLoadingActive ? (
            <ListSkeleton count={1} showAvatar={false} />
          ) : (
            <Box sx={{ textAlign: 'center', color: 'fg.muted' }}>
              <Text as="p" sx={{ fontWeight: 'bold' }}>当前没有进行中的任务。</Text>
              <Text as="p" sx={{ fontSize: 1 }}>上传后任务会出现在这里，可点击进入查看进度。</Text>
            </Box>
          )
        ) : (
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                {isLoadingActive ? (
                  <Label variant="secondary">刷新中...</Label>
                ) : (
                  <Label variant="secondary">进行中 {activeTaskItems.length} 条</Label>
                )}
              </Box>
            </Box>
            <Box as="ul" sx={{ listStyle: 'none', p: 0, m: 0, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              {activeTaskItems.map((t) => (
                <Box as="li" key={t.id}>
                  <Link href={`/tasks/${t.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                    <Box
                      sx={{
                        cursor: 'pointer',
                        borderRadius: 2,
                        overflow: 'hidden',
                        '&:hover': { bg: 'canvas.subtle' },
                      }}
                    >
                      <TaskThumbnail asset={t.asset} size="medium" />
                    </Box>
                  </Link>
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </Box>

      {/* Library Filter */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2}}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Library</Text>
            <Heading as="h2" sx={{ fontSize: 3 }}>题库总览</Heading>
          </Box>
          {isLoading && <Spinner size="small" />}
        </Box>

        <Box sx={{ display: 'grid', gridTemplateColumns: ['1fr', '1fr 1fr'], gap: 3, mb: 3 }}>
          <FormControl>
            <FormControl.Label>学科</FormControl.Label>
            <Select value={subject} onChange={(e) => setSubject(e.target.value)} block>
              {SUBJECT_OPTIONS.map((option) => (
                <Select.Option key={option.value || "all"} value={option.value}>
                  {option.label}
                </Select.Option>
              ))}
            </Select>
          </FormControl>
        </Box>

        <TagSelectorRow
          sourceValue={sourceFilter}
          onSourceChange={setSourceFilter}
          knowledgeValue={knowledgeFilter}
          onKnowledgeChange={setKnowledgeFilter}
          errorValue={errorFilter}
          onErrorChange={setErrorFilter}
          customValue={customFilter}
          onCustomChange={setCustomFilter}
          styles={tagStyles}
          // placeholders={{
          //   knowledge: "输入知识点关键词进行筛选",
          //   error: "输入错因关键词进行筛选",
          //   custom: "输入自定义标签进行筛选",
          // }}
        />

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Label variant="secondary">共 {items.length} 道题</Label>
        </Box>

        {items.length === 0 ? (
          isLoading ? (
            <ListSkeleton count={5} showAvatar={false} />
          ) : (
            <Box sx={{ textAlign: 'center', p: 4, color: 'fg.muted' }}>
              <Text as="p" sx={{ fontWeight: 'bold' }}>暂无题目。</Text>
              <Text as="p" sx={{ fontSize: 1 }}>可以先在首页上传一张手稿图片，生成几道题后再回到这里查看。</Text>
            </Box>
          )
        ) : (
          <Box>
            <Box as="ul" sx={{ listStyle: 'none', p: 0, m: 0 }}>
              {items.map((item) => (
                <Box
                  as="li"
                  key={`${item.task_id}-${item.problem_id}`}
                  sx={{
                    px: 2,
                    py: 2,
                    borderBottom: '1px solid',
                    borderColor: 'border.muted',
                  }}
                >
                  <ProblemListItem
                    item={item}
                    selected={!!selectedIds[`${item.task_id}:${item.problem_id}`]}
                    toggleKey={`${item.task_id}:${item.problem_id}`}
                    onToggleSelection={toggleSelected}
                    showCheckbox
                    showViewLink
                  />
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </Box>

      {/* Results */}

    </Box>
  );
}
