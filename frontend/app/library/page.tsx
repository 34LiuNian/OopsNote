"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ListChecks, Trash2 } from "lucide-react";
import {
  Box,
  Text,
  Select,
  TextInput,
  FormControl,
  Spinner,
  Button,
} from "@/components/ui/primitives";
import { notify } from "@/lib/notify";
import { formatApiError } from "@/lib/errorFormatter";
import { deleteTasks, useActiveTaskList, useProblemList, useTaskList } from "../../features/tasks";
import { ProblemListItem } from "../../components/ProblemListItem";
import { TaskThumbnail } from "../../components/TaskThumbnail";
import { FailedTaskPanel } from "../../components/task/FailedTaskPanel";
import { TagSelectorRow } from "../../components/TagSelectorRow";
import { ListSkeleton } from "../../components/ui/LoadingStates";
import { useTagDimensions } from "../../features/tags";
import { SUBJECT_OPTIONS } from "../../config/subjects";
import { PageHeader } from "@/components/layout/PageHeader";

const LIBRARY_SUBJECT_OPTIONS = [
  { value: "", label: "全部学科" },
  ...SUBJECT_OPTIONS,
];

const TASK_STRIP_CONTENT_MIN_HEIGHT = 84;

function problemSelectionKey(taskId: string, problemId: string) {
  return `${taskId}:${problemId}`;
}

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
    refresh: refreshProblems,
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
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);

  const selectedItems = items.filter((item) => (
    selectedIds[problemSelectionKey(item.task_id, item.problem_id)]
  ));
  const selectedCount = selectedItems.length;
  const allSelected = items.length > 0 && selectedCount === items.length;

  const toggleSelected = useCallback((key: string) => {
    setSelectedIds((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const leaveSelectionMode = useCallback(() => {
    setSelectionMode(false);
    setSelectedIds({});
  }, []);

  const deleteSelected = useCallback(async () => {
    const selected = items.filter((item) => (
      selectedIds[problemSelectionKey(item.task_id, item.problem_id)]
    ));
    if (selected.length === 0 || isBatchDeleting) return;
    if (!window.confirm(`删除选中的 ${selected.length} 道题？对应任务记录也会删除，此操作无法撤销。`)) return;

    setIsBatchDeleting(true);
    const results = await deleteTasks(selected.map((item) => item.task_id));
    const failedKeys: Record<string, boolean> = {};
    results.forEach((result, index) => {
      if (result.status === "rejected") {
        const item = selected[index];
        failedKeys[problemSelectionKey(item.task_id, item.problem_id)] = true;
      }
    });
    const failedCount = Object.keys(failedKeys).length;
    const successCount = selected.length - failedCount;

    if (successCount > 0) notify.success({ title: `已删除 ${successCount} 道题` });
    if (failedCount > 0) {
      const firstFailure = results.find((result) => result.status === "rejected");
      notify.error({
        title: `${failedCount} 道题未能删除`,
        description: firstFailure?.status === "rejected"
          ? formatApiError(firstFailure.reason, "请检查任务状态后重试")
          : undefined,
      });
      setSelectedIds(failedKeys);
    } else {
      leaveSelectionMode();
    }

    try {
      await refreshProblems();
    } finally {
      setIsBatchDeleting(false);
    }
  }, [isBatchDeleting, items, leaveSelectionMode, refreshProblems, selectedIds]);

  // 显示错误通知
  useEffect(() => {
    if (error) {
      notify.error({ title: error });
    }
  }, [error]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {/* Page header */}
      <PageHeader
        title="题库"
        description="浏览、搜索和管理你的错题集"
        action={isLoading ? <Spinner size="small" /> : undefined}
      />

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
              {(taskStripTab === "active" ? isLoadingActive : isLoadingFailed) && (
                <Spinner size="small" />
              )}
            </Box>
            {taskStripTab === "failed" ? (
              <FailedTaskPanel
                tasks={failedTaskItems}
                isLoading={isLoadingFailed}
                refreshFailedTasks={refreshFailedTasks}
                refreshActiveTasks={refreshActiveTasks}
              />
            ) : (
              <Box
                sx={{
                  minHeight: TASK_STRIP_CONTENT_MIN_HEIGHT,
                  display: "flex",
                  alignItems: "center",
                }}
              >
              {activeTaskItems.length > 0 ? (
                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                {activeTaskItems.map((t) => (
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
                ))}
                </Box>
              ) : isLoadingActive ? (
                <Box sx={{ width: "100%", display: "flex", justifyContent: "center" }}>
                  <Spinner size="small" />
                </Box>
              ) : (
                <Text sx={{ color: "fg.muted", fontSize: 1 }}>
                  当前没有{taskStripTab === "active" ? "进行中" : "失败"}任务
                </Text>
              )}
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
            <Select value={subject} onValueChange={(value) => {
              setSubject(value);
              setSelectedIds({});
            }} block>
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
                onChange={(e) => {
                  setDateAfter(e.target.value);
                  setSelectedIds({});
                }}
                sx={{ flex: 1 }}
                placeholder="起始日期"
              />
              <Text sx={{ color: 'fg.muted', flexShrink: 0 }}>至</Text>
              <TextInput
                type="date"
                value={dateBefore}
                onChange={(e) => {
                  setDateBefore(e.target.value);
                  setSelectedIds({});
                }}
                sx={{ flex: 1 }}
                placeholder="结束日期"
              />
              {(dateAfter || dateBefore) && (
                <Button
                  size="small"
                  variant="invisible"
                  onClick={() => {
                    setDateAfter('');
                    setDateBefore('');
                    setSelectedIds({});
                  }}
                >
                  清空
                </Button>
              )}
            </Box>
          </FormControl>
        </Box>

        <TagSelectorRow
          sourceValue={sourceFilter}
          onSourceChange={(value) => {
            setSourceFilter(value);
            setSelectedIds({});
          }}
          knowledgeValue={knowledgeFilter}
          onKnowledgeChange={(value) => {
            setKnowledgeFilter(value);
            setSelectedIds({});
          }}
          errorValue={errorFilter}
          onErrorChange={(value) => {
            setErrorFilter(value);
            setSelectedIds({});
          }}
          customValue={customFilter}
          onCustomChange={(value) => {
            setCustomFilter(value);
            setSelectedIds({});
          }}
          styles={tagStyles}
        />
      </Box>

      {/* Results */}
      <Box>
        {/* Toolbar */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, flexWrap: "wrap", mb: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Text sx={{ fontWeight: 600, fontSize: 2 }}>题目列表</Text>
            <Box className="oops-badge oops-badge-muted">{items.length} 题</Box>
          </Box>
          {selectionMode ? (
            <Box
              role="toolbar"
              aria-label="批量操作题库题目"
              sx={{ display: 'flex', alignItems: "center", gap: 2, flexWrap: "wrap" }}
            >
              <Text sx={{ fontSize: 1, fontWeight: 600 }} aria-live="polite">
                已选 {selectedCount} 项
              </Text>
              <Button
                size="small"
                variant="invisible"
                disabled={isBatchDeleting || items.length === 0}
                onClick={() => {
                  if (allSelected) {
                    setSelectedIds({});
                    return;
                  }
                  setSelectedIds(Object.fromEntries(items.map((item) => [
                    problemSelectionKey(item.task_id, item.problem_id),
                    true,
                  ])));
                }}
              >
                {allSelected ? "取消全选" : "全选"}
              </Button>
              <Button
                size="small"
                variant="invisible"
                disabled={isBatchDeleting || items.length === 0}
                onClick={() => setSelectedIds(Object.fromEntries(items.flatMap((item) => {
                  const key = problemSelectionKey(item.task_id, item.problem_id);
                  return selectedIds[key] ? [] : [[key, true]];
                })))}
              >
                反选
              </Button>
              <Button
                size="small"
                variant="danger"
                leadingVisual={Trash2}
                disabled={selectedCount === 0 || isBatchDeleting}
                onClick={() => void deleteSelected()}
              >
                {isBatchDeleting ? "正在删除…" : `删除 (${selectedCount})`}
              </Button>
              <Button size="small" variant="invisible" disabled={isBatchDeleting} onClick={leaveSelectionMode}>
                取消
              </Button>
            </Box>
          ) : (
            <Button
              size="small"
              variant="secondary"
              leadingVisual={ListChecks}
              onClick={() => {
                setSelectedIds({});
                setSelectionMode(true);
              }}
              disabled={items.length === 0}
            >
              批量操作
            </Button>
          )}
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
                  borderBottomWidth: idx < items.length - 1 ? 1 : 0,
                  borderBottomStyle: 'solid',
                  borderBottomColor: 'border.muted',
                }}
              >
                <ProblemListItem
                  item={item}
                  selected={!!selectedIds[problemSelectionKey(item.task_id, item.problem_id)]}
                  toggleKey={selectionMode ? problemSelectionKey(item.task_id, item.problem_id) : undefined}
                  onToggleSelection={selectionMode ? toggleSelected : undefined}
                  showCheckbox={selectionMode}
                  showViewLink={!selectionMode}
                />
              </Box>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
}
