"use client";

import { Fragment } from "react";
import { Box, Text, Spinner, Octicon } from "@primer/react";
import { CheckIcon, XIcon, SkipIcon } from "@primer/octicons-react";
import { PROGRESS_STEPS, UseTaskProgressResult } from "@/hooks/useTaskProgress";

interface TaskProgressBarProps {
  progressState: UseTaskProgressResult;
  latestLine?: string;
  error?: string;
  statusMessage?: string;
}

// 状态颜色规范（使用 Primer 语义化 token，适配亮暗模式）
const STATUS_COLORS = {
  success: "var(--fgColor-success, #2da44e)",
  error: "var(--fgColor-danger, #cf222e)",
  processing: "var(--fgColor-accent, #0969da)",
  wait: "var(--fgColor-muted, #8c959f)",
} as const;

interface NodeStyle {
  left: string;
  transform: string;
  textAlign: "left" | "center" | "right";
}

function getNodeStyle(idx: number, total: number): NodeStyle {
  if (idx === 0) {
    return { left: "0", transform: "translateX(0)", textAlign: "left" };
  }
  if (idx === total - 1) {
    return { left: "100%", transform: "translateX(-100%)", textAlign: "right" };
  }
  return {
    left: `${(idx / (total - 1)) * 100}%`,
    transform: "translateX(-50%)",
    textAlign: "center",
  };
}

function getNodeStatus(
  idx: number,
  progressState: UseTaskProgressResult,
  isCancelled: boolean
): keyof typeof STATUS_COLORS {
  const isError = progressState.isFailed && progressState.highestIndex === idx;
  const isDone = progressState.highestIndex >= idx;
  const isActive = progressState.activeIndex === idx;
  if (isError) return "error";
  if (isCancelled) return "wait";
  if (isActive) return "processing";
  if (isDone) return "success";
  return "wait";
}

function NodeDot({ status }: { status: keyof typeof STATUS_COLORS }) {
  const color = STATUS_COLORS[status];
  return (
    <Box
      sx={{
        width: 22,
        height: 22,
        borderRadius: "50%",
        border: "2px solid",
        borderColor: color,
        bg: status === "processing" ? "canvas.default" : color,
        color: "canvas.default",
        fontSize: 0,
        fontWeight: 700,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: status === "processing" ? `0 0 0 0.25rem ${color}40` : "none",
        transition: "all 0.4s ease-in-out",
        animation: status === "processing" ? "pulse 1.5s ease-in-out infinite" : "none",
        opacity: status === "wait" ? 0.5 : 1,
        flexShrink: 0,
      }}
    >
      {status === "error" && <Octicon icon={XIcon} size={14} sx={{ animation: "fadeIn 0.3s ease-in-out" }} />}
      {status === "success" && <Octicon icon={CheckIcon} size={14} sx={{ animation: "fadeIn 0.3s ease-in-out" }} />}
      {status === "processing" && <Spinner size="small" sx={{ animation: "fadeIn 0.3s ease-in-out" }} />}
      {status === "wait" && <Octicon icon={SkipIcon} size={14} sx={{ opacity: 0.3 }} />}
    </Box>
  );
}

export function TaskProgressBar({ progressState, latestLine, error, statusMessage }: TaskProgressBarProps) {
  const isCancelled = progressState.isCancelled;

  return (
    <Box sx={{ p: 2, border: "1px solid", borderColor: "border.default", borderRadius: 2, mb: 3 }}>
      {/* ── Desktop horizontal layout ── */}
      <Box sx={{ display: ["none", "block"] }}>
        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
          {PROGRESS_STEPS.map((step, idx) => {
            const nodeStatus = getNodeStatus(idx, progressState, isCancelled);
            const lineToNext = idx < PROGRESS_STEPS.length - 1;
            const isLineDone = progressState.highestIndex > idx && !isCancelled;
            const isCurrentErrorLine = progressState.isFailed && progressState.highestIndex === idx + 1;
            const isLastDoneLine = progressState.highestIndex === idx + 1 && !isCancelled;

            return (
              <Fragment key={step.key}>
                <NodeDot status={nodeStatus} />
                {lineToNext && (
                  <Box
                    sx={{
                      flex: 1,
                      height: 3,
                      mx: 1,
                      bg: isCurrentErrorLine ? STATUS_COLORS.error : isLineDone ? STATUS_COLORS.success : STATUS_COLORS.wait,
                      transition: "all 0.4s ease-in-out",
                      position: "relative",
                      overflow: "hidden",
                      borderRadius: 1,
                    }}
                  >
                    {isLineDone && !isCurrentErrorLine && (
                      <Box
                        sx={{
                          position: "absolute",
                          top: 0,
                          left: 0,
                          height: "100%",
                          bg: STATUS_COLORS.success,
                          width: "100%",
                          animation: isLastDoneLine ? "progressLine 1s cubic-bezier(0.4, 0, 0.2, 1) forwards" : "none",
                        }}
                      />
                    )}
                  </Box>
                )}
              </Fragment>
            );
          })}
        </Box>

        {/* Desktop text labels */}
        <Box sx={{ position: "relative", height: "40px" }}>
          {PROGRESS_STEPS.map((step, idx) => {
            const nodeStatus = getNodeStatus(idx, progressState, isCancelled);
            const isDisabled = (progressState.isFailed || isCancelled) && progressState.highestIndex < idx;
            const isDone = progressState.highestIndex >= idx;
            const isActive = progressState.activeIndex === idx;
            const isError = progressState.isFailed && progressState.highestIndex === idx;
            const textColor = STATUS_COLORS[nodeStatus];
            const subtitle = isError
              ? (error || statusMessage || "处理失败")
              : isCancelled
                ? "已作废"
                : isActive
                  ? (latestLine || progressState.latestLine)
                  : isDone
                    ? "已完成"
                    : isDisabled
                      ? "已阻断"
                      : "等待中";
            const style = getNodeStyle(idx, PROGRESS_STEPS.length);
            return (
              <Box
                key={step.key}
                sx={{
                  position: "absolute",
                  left: style.left,
                  transform: style.transform,
                  textAlign: style.textAlign,
                  minWidth: "80px",
                }}
              >
                <Text sx={{ display: "block", fontSize: 1, fontWeight: 600, color: textColor, transition: "all 0.4s ease-in-out", opacity: isDisabled ? 0.5 : 1, animation: nodeStatus === "processing" ? "fadeIn 0.3s ease-in-out" : "none" }}>
                  {step.title}
                </Text>
                <Text sx={{ display: "block", fontSize: 0, color: isDisabled ? STATUS_COLORS.wait : "var(--fgColor-muted, #8c959f)", mt: 1, transition: "all 0.4s ease-in-out" }}>
                  {subtitle}
                </Text>
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* ── Mobile vertical layout ── */}
      <Box sx={{ display: ["flex", "none"], flexDirection: "column", gap: 0 }}>
        {PROGRESS_STEPS.map((step, idx) => {
          const nodeStatus = getNodeStatus(idx, progressState, isCancelled);
          const isDisabled = (progressState.isFailed || isCancelled) && progressState.highestIndex < idx;
          const isDone = progressState.highestIndex >= idx;
          const isActive = progressState.activeIndex === idx;
          const isError = progressState.isFailed && progressState.highestIndex === idx;
          const textColor = STATUS_COLORS[nodeStatus];
          const subtitle = isError
            ? (error || statusMessage || "处理失败")
            : isCancelled
              ? "已作废"
              : isActive
                ? (latestLine || progressState.latestLine)
                : isDone
                  ? "已完成"
                  : isDisabled
                    ? "已阻断"
                    : "等待中";
          const isLast = idx === PROGRESS_STEPS.length - 1;
          const isLineDone = progressState.highestIndex > idx && !isCancelled;
          const isCurrentErrorLine = progressState.isFailed && progressState.highestIndex === idx + 1;

          return (
            <Box key={step.key} sx={{ display: "flex", alignItems: "stretch", gap: 2 }}>
              {/* Left rail: dot + vertical line */}
              <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", width: "22px", flexShrink: 0 }}>
                <NodeDot status={nodeStatus} />
                {!isLast && (
                  <Box sx={{
                    flex: 1,
                    width: 3,
                    my: "2px",
                    bg: isCurrentErrorLine ? STATUS_COLORS.error : isLineDone ? STATUS_COLORS.success : STATUS_COLORS.wait,
                    borderRadius: 1,
                    transition: "all 0.4s ease-in-out",
                    minHeight: "12px",
                  }} />
                )}
              </Box>
              {/* Right: text */}
              <Box sx={{ py: "2px", pb: isLast ? 0 : 2, minWidth: 0 }}>
                <Text sx={{ display: "block", fontSize: 1, fontWeight: 600, color: textColor, opacity: isDisabled ? 0.5 : 1 }}>
                  {step.title}
                </Text>
                <Text sx={{ display: "block", fontSize: 0, color: isDisabled ? STATUS_COLORS.wait : "var(--fgColor-muted, #8c959f)", mt: "2px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "calc(100vw - 100px)" }}>
                  {subtitle}
                </Text>
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
