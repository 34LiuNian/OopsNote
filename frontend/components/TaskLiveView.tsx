"use client";

import Image from "next/image";
import { useCallback, useState } from "react";
import Link from "next/link";
import { Modal } from "@mantine/core";
import {
  Box,
  Button,
  Heading,
  Text,
  Spinner,
} from "@/components/ui/primitives";
import { fetchJson } from "@/lib/api";
import { useAuthenticatedAssetUrl } from "@/hooks/useAuthenticatedAssetUrl";
import { confirmAction } from "@/lib/confirm";
import type { TaskResponse, TaskRunSummary } from "@/types/api";
import { TaskActions } from "./task/TaskActions";
import { TaskProblemDetail } from "./task/TaskProblemList";
import { deleteTask } from "@/features/tasks";
import { useTagDimensions } from "@/features/tags";
import { useTaskStream } from "@/hooks/useTaskStream";
import { useTaskProgress } from "@/hooks/useTaskProgress";
import { TaskProgressBar } from "./task/TaskProgressBar";
import { ErrorBanner } from "./ui/ErrorBanner";
import { TaskLiveStream } from "./task/TaskLiveStream";
import { TaskMathRenderer } from "./task/TaskMathRenderer";
import { TaskStatusNotifications } from "./task/TaskStatusNotifications";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from "./ui/icons";
import { ProblemStudyPanel } from "./task/ProblemStudyPanel";

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

export function TaskLiveView({ taskId }: { taskId: string }) {
  const [error, setError] = useState<string>("");
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const { effectiveDimensions: tagStyles } = useTagDimensions();
  const [editingKey, setEditingKey] = useState<string>("");
  const [isScreenshotOpen, setIsScreenshotOpen] = useState(false);
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
  const isCompleted = viewData?.task?.status === "completed";
  const duration = runDuration(viewData?.task?.run);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4, width: "100%", maxWidth: 1320, mx: "auto" }}>
      {/* Math renderer */}
      <TaskMathRenderer data={viewData} />

      <TaskStatusNotifications taskId={taskId} statusMessage={statusMessage} status={viewData?.task?.status} />

      {/* Task header card */}
      <Box
        className="oops-card"
        sx={{ p: isCompleted ? 3 : 4, position: "relative", overflow: "hidden" }}
      >
        {/* Subtle gradient accent bar at top */}
        <Box
          sx={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            background: viewData?.task?.status === "completed"
              ? "linear-gradient(90deg, var(--fgColor-success, #2da44e), var(--fgColor-done, #8250df))"
              : viewData?.task?.status === "failed"
                ? "linear-gradient(90deg, var(--fgColor-danger, #cf222e), var(--fgColor-attention, #bf8700))"
                : "linear-gradient(90deg, var(--fgColor-accent, #0969da), var(--fgColor-done, #8250df))",
            borderRadius: "var(--oops-radius-md) var(--oops-radius-md) 0 0",
          }}
        />

        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: isCompleted ? "center" : "flex-start", gap: 3, flexWrap: "wrap" }}>
          <Box sx={{ flex: 1, minWidth: 200 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: isCompleted ? 0 : 1, flexWrap: "wrap" }}>
              <Heading as="h2" sx={{ fontSize: isCompleted ? 2 : 3, m: 0 }}>任务详情</Heading>
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
                  sx={{ px: 1, color: "var(--fgColor-success)" }}
                  leadingVisual={CheckIcon}
                  trailingVisual={showTaskDetails ? ChevronUpIcon : ChevronDownIcon}
                >
                  5/5 阶段完成{duration ? ` · ${duration}` : ""}
                </Button>
              )}
            </Box>
            {(!isCompleted || showTaskDetails) && (
              <Box sx={{ mt: 1 }}>
                <Text sx={{ fontSize: 0, color: "fg.muted", fontFamily: "mono" }}>{taskId}</Text>
                {viewData?.task?.created_at && (
                  <Box sx={{ mt: 2, display: "flex", gap: 3, flexWrap: "wrap" }}>
                    <Text sx={{ fontSize: 0, color: "fg.muted" }}>
                      创建：{new Date(viewData.task.created_at).toLocaleString("zh-CN")}
                    </Text>
                    {duration && (
                      <Text sx={{ fontSize: 0, color: "fg.muted" }}>
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
          <Box sx={{ mt: 3 }}>
            <TaskProgressBar
              progressState={progressState}
              latestLine={progressState.latestLine}
              error={error}
              statusMessage={statusMessage}
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

      <ErrorBanner message={error} />

      {(viewData?.task?.status === "pending" || viewData?.task?.status === "processing") && (
        <TaskLiveStream streamProgress={streamProgress} />
      )}

      {!error && !viewData && (
        <Box className="oops-empty-state" sx={{ py: 6 }}>
          <Spinner size="medium" />
          <Text as="p" sx={{ color: "fg.muted" }}>正在加载任务数据...</Text>
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
        />
      )}

      {viewData?.task.problem && (
        <ProblemStudyPanel
          taskId={taskId}
          problem={viewData.task.problem}
          mergedInto={viewData.task.merged_into}
          onStatusMessage={setStatusMessage}
          onError={setError}
          onRefresh={loadOnce}
          section="variations"
        />
      )}

      {/* Bottom navigation */}
      <Box sx={{ display: "flex", gap: 3, pt: 2, borderTopWidth: 1, borderTopStyle: "solid", borderTopColor: "border.muted", fontSize: 1 }}>
        <Link href="/" style={{ textDecoration: "none" }}>
          <Text as="span" sx={{ color: "accent.fg", fontWeight: 500, "&:hover": { textDecoration: "underline" } }}>← 采集面板</Text>
        </Link>
        <Link href="/library" style={{ textDecoration: "none" }}>
          <Text as="span" sx={{ color: "accent.fg", fontWeight: 500, "&:hover": { textDecoration: "underline" } }}>题库总览</Text>
        </Link>
      </Box>
    </Box>
  );
}
