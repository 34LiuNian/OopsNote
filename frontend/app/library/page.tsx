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
  Button,
} from "@primer/react";
import { sileo } from "sileo";
import { useEffect } from "react";
import { useActiveTaskList, useProblemList } from "../../features/tasks";
import { ProblemListItem } from "../../components/ProblemListItem";
import { TaskThumbnail } from "../../components/TaskThumbnail";
import { TagSelectorRow } from "../../components/TagSelectorRow";
import { ListSkeleton } from "../../components/ui/LoadingStates";
import { useTagDimensions } from "../../features/tags";
import { SUBJECT_OPTIONS } from "../../config/subjects";

const LIBRARY_SUBJECT_OPTIONS = [
  { value: "", label: "全部学科" },
  ...SUBJECT_OPTIONS,
];

export default function LibraryPage() {
  const [subject, setSubject] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [knowledgeFilter, setKnowledgeFilter] = useState<string[]>([]);
  const [errorFilter, setErrorFilter] = useState<string[]>([]);
  const [customFilter, setCustomFilter] = useState<string[]>([]);
  const [dateAfter, setDateAfter] = useState<string>("");
  const [dateBefore, setDateBefore] = useState<string>("");
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
    created_after: dateAfter || undefined,
    created_before: dateBefore || undefined,
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
      {/* Page header */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Box>
          <Heading as="h1" sx={{ fontSize: 4, m: 0 }}>题库</Heading>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>浏览、搜索和管理你的错题集</Text>
        </Box>
        {isLoading && <Spinner size="small" />}
      </Box>

      {/* Active Tasks - compact strip */}
      {(activeTaskItems.length > 0 || isLoadingActive) && (
        <Box
          className="oops-card"
          sx={{ px: 3, py: 2 }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 3, flexWrap: "wrap" }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bg: "success.fg",
                  animation: "pulse 2s ease-in-out infinite",
                }}
              />
              <Text sx={{ fontWeight: 600, fontSize: 1 }}>
                进行中 {activeTaskItems.length} 个任务
              </Text>
            </Box>
            {isLoadingActive ? (
              <Spinner size="small" />
            ) : (
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                {activeTaskItems.map((t) => (
                  <Link key={t.id} href={`/tasks/${t.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                    <Box
                      sx={{
                        cursor: 'pointer',
                        borderRadius: "var(--oops-radius-sm)",
                        overflow: 'hidden',
                        border: "1px solid",
                        borderColor: "border.default",
                        transition: "all var(--oops-transition-fast)",
                        '&:hover': { boxShadow: "var(--oops-shadow-md)", transform: "scale(1.05)" },
                      }}
                    >
                      <TaskThumbnail asset={t.asset} size="medium" />
                    </Box>
                  </Link>
                ))}
              </Box>
            )}
          </Box>
        </Box>
      )}

      {/* Filters */}
      <Box className="oops-card" sx={{ p: 3 }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: ['1fr', '1fr 1fr'], gap: 3, mb: 3 }}>
          <FormControl>
            <FormControl.Label>学科</FormControl.Label>
            <Select value={subject} onChange={(e) => setSubject(e.target.value)} block>
                {LIBRARY_SUBJECT_OPTIONS.map((option) => (
                <Select.Option key={option.value || "all"} value={option.value}>
                  {option.label}
                </Select.Option>
              ))}
            </Select>
          </FormControl>
          <FormControl>
            <FormControl.Label>日期范围</FormControl.Label>
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
              <TextInput
                type="date"
                value={dateAfter}
                onChange={(e) => setDateAfter(e.target.value)}
                sx={{ flex: 1 }}
                placeholder="起始日期"
              />
              <Text sx={{ color: 'fg.muted', flexShrink: 0 }}>至</Text>
              <TextInput
                type="date"
                value={dateBefore}
                onChange={(e) => setDateBefore(e.target.value)}
                sx={{ flex: 1 }}
                placeholder="结束日期"
              />
              {(dateAfter || dateBefore) && (
                <Button
                  size="small"
                  variant="invisible"
                  onClick={() => { setDateAfter(''); setDateBefore(''); }}
                >
                  清空
                </Button>
              )}
            </Box>
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
        />
      </Box>

      {/* Results */}
      <Box>
        {/* Toolbar */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Text sx={{ fontWeight: 600, fontSize: 2 }}>题目列表</Text>
            <Box className="oops-badge oops-badge-muted">{items.length} 题</Box>
          </Box>
          <Box sx={{ display: 'flex', gap: 2 }}>
            {Object.keys(selectedIds).filter((k) => selectedIds[k]).length > 0 && (
              <Button 
                size="small"
                variant="invisible"
                onClick={() => setSelectedIds({})}
              >
                取消选择 ({Object.keys(selectedIds).filter((k) => selectedIds[k]).length})
              </Button>
            )}
            <Button 
              size="small"
              variant="invisible"
              onClick={() => {
                const allSelected: Record<string, boolean> = {};
                items.forEach((item) => {
                  allSelected[`${item.task_id}:${item.problem_id}`] = true;
                });
                setSelectedIds(allSelected);
              }}
              disabled={items.length === 0}
            >
              全选
            </Button>
          </Box>
        </Box>

        {items.length === 0 ? (
          isLoading ? (
            <ListSkeleton count={5} showAvatar={false} />
          ) : (
            <Box className="oops-empty-state">
              <Text as="p" sx={{ fontWeight: 600, fontSize: 2 }}>暂无题目</Text>
              <Text as="p" sx={{ fontSize: 1 }}>在首页上传手稿图片，AI 会自动识别并生成题目。</Text>
              <Link href="/" style={{ textDecoration: "none" }}>
                <Button variant="primary" sx={{ mt: 2 }}>去上传</Button>
              </Link>
            </Box>
          )
        ) : (
          <Box sx={{ display: "flex", flexDirection: "column" }}>
            {items.map((item, idx) => (
              <Box
                key={`${item.task_id}-${item.problem_id}`}
                className="oops-list-item"
                sx={{
                  px: 2,
                  py: 2,
                  borderBottom: idx < items.length - 1 ? '1px solid' : 'none',
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
        )}
      </Box>
    </Box>
  );
}
