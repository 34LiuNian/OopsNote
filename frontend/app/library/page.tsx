"use client";

import { useCallback, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { ListChecks, RotateCcw, SlidersHorizontal, Trash2 } from "lucide-react";
import {
  Box,
  Text,
  Spinner,
  Button,
} from "@/components/ui/primitives";
import { notify } from "@/lib/notify";
import { confirmAction } from "@/lib/confirm";
import { formatApiError } from "@/lib/errorFormatter";
import { deleteTasks, useActiveTaskList, useProblemList, useTaskList } from "../../features/tasks";
import { ProblemListItem } from "../../components/ProblemListItem";
import { TaskThumbnail } from "../../components/TaskThumbnail";
import { FailedTaskPanel } from "../../components/task/FailedTaskPanel";
import { ListSkeleton } from "../../components/ui/LoadingStates";
import { useTagDimensions } from "../../features/tags";
import { PageHeader } from "@/components/layout/PageHeader";
import { useSecondarySidebar } from "@/components/layout/SecondarySidebarContext";
import { LibraryFilterPanel } from "@/components/library/LibraryFilterPanel";
import sxStyles from "./page.sx.module.css";

const TASK_STRIP_CONTENT_MIN_HEIGHT = 84;
const TASK_STRIP_STYLE = { "--oops-geometry-min-height": `${TASK_STRIP_CONTENT_MIN_HEIGHT}px` } as React.CSSProperties;

function problemSelectionKey(taskId: string, problemId: string) {
  return `${taskId}:${problemId}`;
}

export default function LibraryPage() {
  const {
    target: secondarySidebarTarget,
    contextSidebarOpen,
    toggleContextSidebar,
    closeSecondarySidebar,
  } = useSecondarySidebar();
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
  const taskStripView = taskStripTab;
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);

  const activeFilterCount = [
    subject,
    dateAfter || dateBefore,
    ...sourceFilter,
    ...knowledgeFilter,
    ...errorFilter,
    ...customFilter,
  ].filter(Boolean).length;

  const clearAllFilters = useCallback(() => {
    setSubject("");
    setSourceFilter([]);
    setKnowledgeFilter([]);
    setErrorFilter([]);
    setCustomFilter([]);
    setDateAfter("");
    setDateBefore("");
    setSelectedIds({});
  }, []);

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

  const performDeleteSelected = useCallback(async () => {
    const selected = items.filter((item) => (
      selectedIds[problemSelectionKey(item.task_id, item.problem_id)]
    ));
    if (selected.length === 0 || isBatchDeleting) return;

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

  const deleteSelected = useCallback(() => {
    const selected = items.filter((item) => (
      selectedIds[problemSelectionKey(item.task_id, item.problem_id)]
    ));
    if (selected.length === 0 || isBatchDeleting) return;
    confirmAction({
      title: "删除题目",
       message: `删除选中的 ${selected.length} 道题？对应任务记录也会删除，此操作无法撤销。`,
      confirmLabel: "删除",
      destructive: true,
      onConfirm: performDeleteSelected,
    });
  }, [isBatchDeleting, items, performDeleteSelected, selectedIds]);

  return (
    <>
      {secondarySidebarTarget ? createPortal(
        <LibraryFilterPanel
          subject={subject}
          onSubjectChange={(value) => {
            setSubject(value);
            setSelectedIds({});
          }}
          dateAfter={dateAfter}
          onDateAfterChange={(value) => {
            setDateAfter(value);
            setSelectedIds({});
          }}
          dateBefore={dateBefore}
          onDateBeforeChange={(value) => {
            setDateBefore(value);
            setSelectedIds({});
          }}
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
          activeCount={activeFilterCount}
          onClearAll={clearAllFilters}
          onClose={closeSecondarySidebar}
        />,
        secondarySidebarTarget,
      ) : null}
    <Box className={sxStyles.sx1}>
      {/* Page header */}
      <PageHeader
        title="题库"
        description="浏览、搜索和管理你的错题集"
        action={isLoading ? <Spinner size="small" /> : undefined}
      />

      {/* Active Tasks - compact strip */}
      {(activeTaskItems.length > 0 || failedTaskItems.length > 0 || isLoadingActive || isLoadingFailed) && (
        <Box
          className={["oops-card", sxStyles.sx2].filter(Boolean).join(" ")}

        >
          <Box className={sxStyles.sx3}>
            <Box className={sxStyles.sx4}>
              <Button
                size="small"
                variant={taskStripView === "active" ? "default" : "invisible"}
                onClick={() => setTaskStripTab("active")}
              >
                进行中 {activeTaskItems.length}
              </Button>
              <Button
                size="small"
                variant={taskStripView === "failed" ? "default" : "invisible"}
                onClick={() => setTaskStripTab("failed")}
              >
                失败 {failedTaskItems.length}
              </Button>
              {(taskStripView === "active" ? isLoadingActive : isLoadingFailed) && (
                <Spinner size="small" />
              )}
            </Box>
            {taskStripView === "failed" ? (
              <FailedTaskPanel
                tasks={failedTaskItems}
                isLoading={isLoadingFailed}
                refreshFailedTasks={refreshFailedTasks}
                refreshActiveTasks={refreshActiveTasks}
              />
            ) : (
              <Box
                className={sxStyles.taskStripContent}
                style={TASK_STRIP_STYLE}
              >
              {activeTaskItems.length > 0 ? (
                <Box className={sxStyles.sx5}>
                {activeTaskItems.map((t) => (
                    <Link key={t.id} href={`/tasks/${t.id}`} className={sxStyles.taskLink}>
                      <Box
                        className={sxStyles.sx6}
                      >
                        <TaskThumbnail asset={t.asset} size="medium" />
                      </Box>
                    </Link>
                ))}
                </Box>
              ) : isLoadingActive ? (
                <Box className={sxStyles.sx7}>
                  <Spinner size="small" />
                </Box>
              ) : (
                <Text className={sxStyles.sx8}>
                  当前没有{taskStripView === "active" ? "进行中" : "失败"}任务
                </Text>
              )}
              </Box>
            )}
          </Box>
        </Box>
      )}

      {/* Results */}
      <Box>
        {/* Toolbar */}
        <Box className={sxStyles.sx9}>
          <Box className={sxStyles.sx10}>
            <Text className={sxStyles.sx11}>题目列表</Text>
            <Box className="oops-badge oops-badge-muted">{items.length} 题</Box>
          </Box>
          {selectionMode ? (
            <Box
              role="toolbar"
              aria-label="批量操作题库题目"
              className={sxStyles.sx12}
            >
              <Text className={sxStyles.sx13} aria-live="polite">
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
            <Box className={sxStyles.sx14}>
              <Button
                className="library-filter-trigger"
                size="small"
                variant={contextSidebarOpen ? "default" : "secondary"}
                leadingVisual={SlidersHorizontal}
                aria-pressed={contextSidebarOpen}
                onClick={toggleContextSidebar}
              >
                {activeFilterCount > 0 ? `筛选 (${activeFilterCount})` : "筛选"}
              </Button>
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
            </Box>
          )}
        </Box>

        {items.length === 0 ? (
          isLoading ? (
            <ListSkeleton count={5} showAvatar={false} />
          ) : error ? (
            <Box className="oops-empty-state">
              <Text as="p" className={sxStyles.sx15}>题库加载失败</Text>
              <Text as="p" className={sxStyles.sx16}>{error || "暂时无法读取题库，请检查连接后重试。"}</Text>
              <Button variant="secondary" leadingVisual={RotateCcw} onClick={() => void refreshProblems()}>重新加载</Button>
            </Box>
          ) : (
            <Box className="oops-empty-state">
              <Text as="p" className={sxStyles.sx15}>暂无题目</Text>
              <Text as="p" className={sxStyles.sx16}>在首页上传手稿图片，AI 会自动识别并生成题目。</Text>
              <Link href="/new" className={sxStyles.taskLink}>
                <Button variant="primary" className={sxStyles.sx17}>去上传</Button>
              </Link>
            </Box>
          )
        ) : (
          <Box className={sxStyles.sx18}>
            {items.map((item, idx) => (
              <Box
                key={`${item.task_id}-${item.problem_id}`}
                className={["oops-list-item", sxStyles.problemItem].join(" ")}
                data-last={idx === items.length - 1 ? "true" : undefined}
              >
                <ProblemListItem
                  item={item}
                  selected={!!selectedIds[problemSelectionKey(item.task_id, item.problem_id)]}
                  toggleKey={selectionMode ? problemSelectionKey(item.task_id, item.problem_id) : undefined}
                  onToggleSelection={selectionMode ? toggleSelected : undefined}
                  showViewLink={!selectionMode}
                  showMetaPills
                  showAnswerPeek={!selectionMode}
                />
              </Box>
            ))}
          </Box>
        )}
      </Box>
    </Box>
    </>
  );
}
