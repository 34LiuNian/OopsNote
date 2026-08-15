"use client";

import Image from "next/image";
import { useCallback, useState } from "react";
import Link from "next/link";
import {
  Box,
  Button,
  Heading,
  Modal,
  Text,
  Spinner,
} from "@/components/ui/primitives";
import { fetchJson } from "@/lib/api";
import { useAuthenticatedAssetUrl } from "@/hooks/useAuthenticatedAssetUrl";
import { confirmAction } from "@/lib/confirm";
import type { DiagramItem, TaskResponse, TaskRunSummary } from "@/types/api";
import { TaskActions } from "./task/TaskActions";
import { TaskProblemDetail } from "./task/TaskProblemList";
import { deleteTask } from "@/features/tasks";
import { useTagDimensions } from "@/features/tags";
import { useTaskStream } from "@/hooks/useTaskStream";
import { DIAGRAM_PROGRESS_STEPS, PROGRESS_STEPS, useTaskProgress } from "@/hooks/useTaskProgress";
import { TaskProgressBar } from "./task/TaskProgressBar";
import { ErrorBanner } from "./ui/ErrorBanner";
import { TaskMathRenderer } from "./task/TaskMathRenderer";
import { TaskStatusNotifications } from "./task/TaskStatusNotifications";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from "./ui/icons";
import { ProblemStudyPanel } from "./task/ProblemStudyPanel";
import sxStyles from "./TaskLiveView.sx.module.css";

function formatDurationMs(diffMs: number): string {
  if (!Number.isFinite(diffMs) || diffMs < 0) return "未知";
  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours > 0) return `${hours}小时${remainingMinutes}分${remainingSeconds}秒`;
  if (minutes > 0) return `${minutes}分${remainingSeconds}秒`;
  return `${remainingSeconds}秒`;
}

function runDuration(run?: TaskRunSummary | null): string | null {
  if (!run) return null;
  if (typeof run.duration_ms === "number" && run.duration_ms >= 0) {
    return formatDurationMs(run.duration_ms);
  }
  if (!run.started_at || !run.ended_at) return null;
  const startedAt = new Date(run.started_at).getTime();
  const endedAt = new Date(run.ended_at).getTime();
  if (!Number.isFinite(startedAt) || !Number.isFinite(endedAt) || endedAt < startedAt) return null;
  return formatDurationMs(endedAt - startedAt);
}

function diagramRunStatus(run: TaskRunSummary | null, item: DiagramItem | null): string {
  if (item?.status === "needs_review" || item?.status === "failed") return "failed";
  if (item?.status === "cancelled" || run?.status === "cancelled") return "cancelled";
  if (run?.status === "failed" || run?.status === "timed_out") return "failed";
  if (run?.status === "queued") return "pending";
  if (run?.status === "running") return "processing";
  if (run?.status === "completed" || item?.status === "ready_tikz" || item?.status === "ready_image") return "completed";
  return "pending";
}

function diagramStage(item: DiagramItem | null, run: TaskRunSummary | null): string {
  if (run?.status === "queued") return "queued";
  if (run?.diagram_step) return run.diagram_step;
  if (item?.status === "generating") return "generate";
  if (item?.status === "rendering") return "render";
  if (item?.status === "reviewing") return "review";
  if (item?.status === "ready_tikz" || item?.status === "ready_image" || item?.status === "needs_review") return "review";
  return "queued";
}

export function TaskLiveView({ taskId }: { taskId: string }) {
  const [error, setError] = useState<string>("");
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const { effectiveDimensions: tagStyles } = useTagDimensions();
  const [editingKey, setEditingKey] = useState<string>("");
  const [isScreenshotOpen, setIsScreenshotOpen] = useState(false);
  const [isVariationOpen, setIsVariationOpen] = useState(false);
  const [showTaskDetails, setShowTaskDetails] = useState(false);

  const {
    data,
    progressLines: streamProgress,
    resetStream,
    refresh: loadOnce,
    isLoading,
    error: streamError,
  } = useTaskStream({
    taskId,
    onStatusMessage: setStatusMessage,
  });
  const viewData = data;
  const streamErrorMessage = streamError instanceof Error ? streamError.message : streamError ?? "";
  const screenshotUrl = useAuthenticatedAssetUrl(viewData?.task.trace?.screenshot_path);

  const cancelTask = useCallback(async () => {
    if (!viewData) return;
    const status = viewData.task.status;
    if (status !== "pending" && status !== "processing") return;

    setIsCancelling(true);
    setError("");
    try {
      await fetchJson<TaskResponse>(`/tasks/${taskId}/cancel`, { method: "POST" });
      await loadOnce();
    } catch (err) {
      setError(err instanceof Error ? err.message : "作废任务失败");
    } finally {
      setIsCancelling(false);
    }
  }, [loadOnce, taskId, viewData]);

  const retryTask = useCallback(async () => {
    if (!viewData) return;
    const status = viewData.task.status;
    if (status !== "failed" && status !== "completed" && status !== "cancelled") return;

    setIsRetrying(true);
    setError("");
    setStatusMessage("准备重试...");
    resetStream();

    try {
      await fetchJson<TaskResponse>(
        `/tasks/${taskId}/retry?background=true`,
        { method: "POST" }
      );
      await loadOnce();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重试失败");
    } finally {
      setIsRetrying(false);
    }
  }, [loadOnce, resetStream, taskId, viewData]);


  const removeTask = useCallback(() => {
    confirmAction({
      title: "删除任务",
      message: "确认删除这个任务及其题目？此操作无法撤销。",
      confirmLabel: "删除",
      destructive: true,
      onConfirm: async () => {
        try {
          await deleteTask(taskId);
          window.location.href = "/library";
        } catch (err) {
          setError(err instanceof Error ? err.message : "删除任务失败");
        }
      },
    });
  }, [taskId]);

  const progressState = useTaskProgress({
    status: viewData?.task?.status,
    stage: viewData?.task?.stage,
    stageMessage: viewData?.task?.stage_message,
    statusMessage,
    streamProgress,
  });
  const diagramItem = viewData?.task.problem?.diagram_items?.[0] ?? null;
  const diagramRun = diagramItem?.active_run_id
    ? viewData?.task.diagram_runs?.find((run) => run.id === diagramItem.active_run_id) ?? null
    : viewData?.task.diagram_runs?.[0] ?? null;
  const diagramStageMessage = diagramRun?.stages.at(-1)?.message ?? diagramItem?.last_error ?? null;
  const diagramProgressState = useTaskProgress({
    status: diagramRunStatus(diagramRun, diagramItem),
    stage: diagramStage(diagramItem, diagramRun),
    stageMessage: diagramStageMessage,
    steps: DIAGRAM_PROGRESS_STEPS,
  });
  const diagramProgressVisible = Boolean(viewData?.task.problem?.has_diagram || diagramItem || diagramRun);
  const diagramNeedsReview = Boolean(diagramItem?.needs_review || diagramItem?.status === "needs_review");
  const isCompleted = viewData?.task?.status === "completed";
  const duration = runDuration(viewData?.task?.run);

  return (
    <Box className={sxStyles.sx1}>
      {/* Math renderer */}
      <TaskMathRenderer data={viewData} />

      <TaskStatusNotifications
        taskId={taskId}
        statusMessage={statusMessage}
        status={viewData?.task?.status}
        progressLines={streamProgress}
      />
      <ErrorBanner message={streamErrorMessage} title="加载任务失败" />

      {/* Task header card */}
      <Box
        className={`oops-card ${sxStyles.headerCard}`}
        data-completed={isCompleted ? "true" : "false"}
      >
        {/* Status is semantic; the bar must not introduce a local palette. */}
        <Box className={sxStyles.statusBar} data-status={viewData?.task?.status ?? "pending"} />

        <Box className={sxStyles.headerRow} data-completed={isCompleted ? "true" : "false"}>
          <Box className={sxStyles.sx2}>
            <Box className={sxStyles.titleRow} data-completed={isCompleted ? "true" : "false"}>
              <Heading as="h2" className={sxStyles.title} data-completed={isCompleted ? "true" : "false"}>任务详情</Heading>
              {!isCompleted && (
                <Box
                  className={`oops-badge ${
                    viewData?.task?.status === "failed" ? "oops-badge-danger"
                      : viewData?.task?.status === "processing" || viewData?.task?.status === "pending" ? "oops-badge-accent"
                        : "oops-badge-muted"
                  }`}
                >
                  {viewData?.task?.status === "failed" ? "失败"
                    : viewData?.task?.status === "processing" ? "处理中"
                      : viewData?.task?.status === "pending" ? "排队中"
                        : viewData?.task?.status === "cancelled" ? "已取消"
                          : viewData?.task?.status ?? "加载中"}
                </Box>
              )}
              {isCompleted && (
                <Button
                  size="small"
                  variant="invisible"
                  onClick={() => setShowTaskDetails((value) => !value)}
                  aria-expanded={showTaskDetails}
                  className={sxStyles.sx3}
                  leadingVisual={CheckIcon}
                  trailingVisual={showTaskDetails ? ChevronUpIcon : ChevronDownIcon}
                >
                  {PROGRESS_STEPS.length}/{PROGRESS_STEPS.length} 阶段完成{duration ? ` · ${duration}` : ""}
                </Button>
              )}
            </Box>
            {(!isCompleted || showTaskDetails) && (
              <Box className={sxStyles.sx4}>
                <Text className={sxStyles.sx5}>{taskId}</Text>
                {viewData?.task?.created_at && (
                  <Box className={sxStyles.sx6}>
                    <Text className={sxStyles.sx7}>
                      创建：{new Date(viewData.task.created_at).toLocaleString("zh-CN")}
                    </Text>
                    {duration && (
                      <Text className={sxStyles.sx8}>
                        用时：{duration}
                      </Text>
                    )}
                  </Box>
                )}
              </Box>
            )}
          </Box>
          <TaskActions
            status={viewData?.task?.status}
            isCancelling={isCancelling}
            isRetrying={isRetrying}
            isLoading={isLoading}
            onCancel={cancelTask}
            onRetry={retryTask}
            onRefresh={loadOnce}
            onDelete={removeTask}
          />
        </Box>
        {(!isCompleted || showTaskDetails) && (
          <Box className={sxStyles.sx9}>
            <TaskProgressBar
              progressState={progressState}
              latestLine={progressState.latestLine}
              error={error}
              statusMessage={statusMessage}
              embedded
            />
          </Box>
        )}
        {diagramProgressVisible && (
          <Box className={sxStyles.sx10}>
            <Box className={sxStyles.sx11}>
              <Text className={sxStyles.sx12}>TikZ 题图重建</Text>
              <Text className={sxStyles.diagramStatus} data-status={diagramNeedsReview ? "review" : diagramProgressState.isCompleted ? "success" : "pending"}>
                {diagramNeedsReview ? "待人工复核" : diagramProgressState.isCompleted ? "已完成" : diagramProgressState.latestLine}
              </Text>
            </Box>
            <TaskProgressBar
              progressState={diagramProgressState}
              latestLine={diagramProgressState.latestLine}
              error={diagramItem?.last_error || diagramRun?.error_message || undefined}
              statusMessage={diagramStageMessage || undefined}
              steps={DIAGRAM_PROGRESS_STEPS}
              embedded
            />
          </Box>
        )}
      </Box>

      {viewData?.task.trace && (
        <Modal opened={isScreenshotOpen} onClose={() => setIsScreenshotOpen(false)} title={viewData.task.trace.kind === "batch_segment" ? "选框截图" : "原图"} centered size="lg">
          {screenshotUrl ? <Image
              className="task-trace-image"
              src={screenshotUrl}
              alt={viewData.task.trace.screenshot_filename ?? "题目图片"}
              width={1280}
              height={760}
              unoptimized
            /> : <Spinner size="small" />}
        </Modal>
      )}

      {viewData?.task.problem && !viewData.task.merged_into && (
        <Modal opened={isVariationOpen} onClose={() => setIsVariationOpen(false)} title="举一反三" centered size="lg">
          <ProblemStudyPanel
            taskId={taskId}
            problem={viewData.task.problem}
            mergedInto={viewData.task.merged_into}
            onStatusMessage={setStatusMessage}
            onError={setError}
            onRefresh={loadOnce}
            section="variations"
          />
        </Modal>
      )}

      <ErrorBanner message={error} />

      {!error && !viewData && (
        <Box className={["oops-empty-state", sxStyles.sx13].filter(Boolean).join(" ")} >
          <Spinner size="medium" />
          <Text as="p" className={sxStyles.sx14}>正在加载任务数据...</Text>
        </Box>
      )}

      {viewData?.task.problem && (
        <ProblemStudyPanel
          taskId={taskId}
          problem={viewData.task.problem}
          mergedInto={viewData.task.merged_into}
          onStatusMessage={setStatusMessage}
          onError={setError}
          onRefresh={loadOnce}
          section="duplicates"
        />
      )}

      {viewData && (
        <TaskProblemDetail
          taskId={taskId}
          taskDifficulty={viewData.task.payload?.difficulty}
          taskAssetPath={viewData.task.asset?.path}
          taskTrace={viewData.task.trace}
          problem={viewData.task.problem}
          solution={viewData.task.solution}
          tag={viewData.task.tag}
          editingKey={editingKey}
          onEdit={setEditingKey}
          onCloseEdit={() => setEditingKey("")}
          onSaved={loadOnce}
          tagStyles={tagStyles}
          onStatusMessage={setStatusMessage}
          onError={setError}
          onOpenSourceImage={() => setIsScreenshotOpen(true)}
          onOpenVariations={() => setIsVariationOpen(true)}
        />
      )}

      {/* Bottom navigation */}
      <Box className={sxStyles.sx15}>
        <Link href="/" className={sxStyles.navLink}>
          <Text as="span" className={sxStyles.sx16}>← 采集面板</Text>
        </Link>
        <Link href="/library" className={sxStyles.navLink}>
          <Text as="span" className={sxStyles.sx17}>题库总览</Text>
        </Link>
      </Box>
    </Box>
  );
}
