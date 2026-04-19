"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import {
  Box,
  Heading,
  Text,
  Label,
  Checkbox,
  Select,
  TextInput,
  FormControl,
  Spinner,
  Button,
} from "@primer/react";
import { notify } from "@/lib/notify";
import { useEffect } from "react";
import { retryTask, useActiveTaskList, useProblemList, useTaskList } from "../../features/tasks";
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

const TASK_STRIP_CONTENT_MIN_HEIGHT = 84;

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
    refresh: refreshActiveTasks,
  } = useActiveTaskList({ active_only: true, subject: subject || undefined });
  const {
    items: failedTaskItems,
    isLoading: isLoadingFailed,
    refresh: refreshFailedTasks,
  } = useTaskList({
    active_only: false,
    status: "failed",
    subject: subject || undefined,
  });
  const [taskStripTab, setTaskStripTab] = useState<"active" | "failed">("active");
  const [selectedFailedTaskIds, setSelectedFailedTaskIds] = useState<Record<string, boolean>>({});
  const [isBatchRetrying, setIsBatchRetrying] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const visibleTaskItems = taskStripTab === "active" ? activeTaskItems : failedTaskItems;
  const isLoadingTaskStrip = taskStripTab === "active" ? isLoadingActive : isLoadingFailed;
  const selectedFailedCount = failedTaskItems.filter((task) => selectedFailedTaskIds[task.id]).length;



  const toggleSelected = useCallback((key: string) => {
    setSelectedIds((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const toggleFailedTaskSelected = useCallback((taskId: string) => {
    setSelectedFailedTaskIds((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  }, []);

  const clearFailedTaskSelection = useCallback(() => {
    setSelectedFailedTaskIds({});
  }, []);

  const selectAllFailedTasks = useCallback(() => {
    const allSelected: Record<string, boolean> = {};
    failedTaskItems.forEach((task) => {
      allSelected[task.id] = true;
    });
    setSelectedFailedTaskIds(allSelected);
  }, [failedTaskItems]);

  const retrySelectedFailedTasks = useCallback(async () => {
    const targetIds = failedTaskItems
      .filter((task) => selectedFailedTaskIds[task.id])
      .map((task) => task.id);

    if (targetIds.length === 0 || isBatchRetrying) return;

    setIsBatchRetrying(true);
    try {
      const results = await Promise.allSettled(targetIds.map((taskId) => retryTask(taskId, true)));
      const successCount = results.filter((r) => r.status === "fulfilled").length;
      const failCount = targetIds.length - successCount;

      if (successCount > 0) {
        notify.success({ title: `已提交 ${successCount} 个任务重试` });
      }
      if (failCount > 0) {
        notify.error({ title: `${failCount} 个任务重试失败` });
      }

      setSelectedFailedTaskIds({});
      await Promise.all([refreshFailedTasks(), refreshActiveTasks()]);
      setTaskStripTab("active");
    } catch (err) {
      notify.error({ title: err instanceof Error ? err.message : "批量重试失败" });
    } finally {
      setIsBatchRetrying(false);
    }
  }, [failedTaskItems, isBatchRetrying, refreshActiveTasks, refreshFailedTasks, selectedFailedTaskIds]);

  // 显示错误通知
  useEffect(() => {
    if (error) {
      notify.error({ title: error });
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
      {(activeTaskItems.length > 0 || failedTaskItems.length > 0 || isLoadingActive || isLoadingFailed) && (
        <Box
          className="oops-card"
          sx={{ px: 3, py: 2 }}
        >
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
              <Button
                size="small"
                variant={taskStripTab === "active" ? "default" : "invisible"}
                onClick={() => setTaskStripTab("active")}
              >
                进行中 {activeTaskItems.length}
              </Button>
              <Button
                size="small"
                variant={taskStripTab === "failed" ? "default" : "invisible"}
                onClick={() => setTaskStripTab("failed")}
              >
                失败 {failedTaskItems.length}
              </Button>
              {taskStripTab === "failed" && failedTaskItems.length > 0 && (
                <>
                  <Button size="small" variant="invisible" onClick={selectAllFailedTasks}>
                    全选
                  </Button>
                  {selectedFailedCount > 0 && (
                    <Button size="small" variant="invisible" onClick={clearFailedTaskSelection}>
                      清空 ({selectedFailedCount})
                    </Button>
                  )}
                  <Button
                    size="small"
                    variant="primary"
                    disabled={selectedFailedCount === 0 || isBatchRetrying}
                    onClick={() => {
                      void retrySelectedFailedTasks();
                    }}
                  >
                    {isBatchRetrying ? "重试中..." : `批量重试 (${selectedFailedCount})`}
                  </Button>
                </>
              )}
              {isLoadingTaskStrip && (
                <Spinner size="small" />
              )}
            </Box>
            <Box
              sx={{
                minHeight: TASK_STRIP_CONTENT_MIN_HEIGHT,
                display: "flex",
                alignItems: "center",
              }}
            >
              {visibleTaskItems.length > 0 ? (
                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                {visibleTaskItems.map((t) => (
                  taskStripTab === "failed" ? (
                    <Box
                      key={t.id}
                      sx={{
                        position: "relative",
                        borderRadius: "var(--oops-radius-sm)",
                        overflow: "hidden",
                        border: "1px solid",
                        borderColor: selectedFailedTaskIds[t.id] ? "accent.fg" : "border.default",
                        transition: "all var(--oops-transition-fast)",
                        bg: "canvas.default",
                      }}
                    >
                      <TaskThumbnail asset={t.asset} size="medium" />
                      <Box
                        sx={{
                          position: "absolute",
                          right: 6,
                          bottom: 6,
                          zIndex: 2,
                          bg: "canvas.default",
                          borderRadius: 6,
                          px: 2,
                          py: 1,
                          border: "1px solid",
                          borderColor: "border.default",
                          boxShadow: "shadow.small",
                          display: "flex",
                          alignItems: "center",
                          gap: 2,
                        }}
                      >
                        <Label
                          sx={{ display: "flex", alignItems: "center", gap: 1, m: 0, cursor: "pointer" }}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                          }}
                        >
                          <Checkbox
                            checked={!!selectedFailedTaskIds[t.id]}
                            onChange={() => toggleFailedTaskSelected(t.id)}
                          />
                          <Text sx={{ fontSize: 0 }}>选中</Text>
                        </Label>
                        <Link href={`/tasks/${t.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                          <Button
                            size="small"
                            variant="invisible"
                            onClick={(e) => {
                              e.stopPropagation();
                            }}
                          >
                            查看
                          </Button>
                        </Link>
                      </Box>
                    </Box>
                  ) : (
                    <Link key={t.id} href={`/tasks/${t.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                      <Box
                        sx={{
                          position: "relative",
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
                  )
                ))}
                </Box>
              ) : isLoadingTaskStrip ? (
                <Box sx={{ width: "100%", display: "flex", justifyContent: "center" }}>
                  <Spinner size="small" />
                </Box>
              ) : (
                <Text sx={{ color: "fg.muted", fontSize: 1 }}>
                  当前没有{taskStripTab === "active" ? "进行中" : "失败"}任务
                </Text>
              )}
            </Box>
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
