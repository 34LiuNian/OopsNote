"use client";

import { Fragment } from "react";
import { Box, Text, Spinner, Octicon } from "@/components/ui/primitives";
import { CheckIcon, XIcon, SkipIcon } from "@/components/ui/icons";
import { PROGRESS_STEPS, ProgressStep, UseTaskProgressResult } from "@/hooks/useTaskProgress";
import sxStyles from "./TaskProgressBar.sx.module.css";

interface TaskProgressBarProps {
  progressState: UseTaskProgressResult;
  latestLine?: string;
  error?: string;
  statusMessage?: string;
  embedded?: boolean;
  steps?: ProgressStep[];
}

type NodeStatus = "success" | "error" | "processing" | "wait";

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
): NodeStatus {
  const isError = progressState.isFailed && progressState.highestIndex === idx;
  const isDone = progressState.highestIndex >= idx;
  const isActive = progressState.activeIndex === idx;
  if (isError) return "error";
  if (isCancelled) return "wait";
  if (isActive) return "processing";
  if (isDone) return "success";
  return "wait";
}

function NodeDot({ status }: { status: NodeStatus }) {
  return (
    <Box
      className={sxStyles.nodeDot}
      data-status={status}
    >
      {status === "error" && <Octicon icon={XIcon} size={14} className={sxStyles.sx1} />}
      {status === "success" && <Octicon icon={CheckIcon} size={14} className={sxStyles.sx2} />}
      {status === "processing" && <Spinner size="small" className={sxStyles.sx3} />}
      {status === "wait" && <Octicon icon={SkipIcon} size={14} className={sxStyles.sx4} />}
    </Box>
  );
}

export function TaskProgressBar({ progressState, latestLine, error, statusMessage, embedded = false, steps = PROGRESS_STEPS }: TaskProgressBarProps) {
  const isCancelled = progressState.isCancelled;

  return (
    <Box className={sxStyles.progressRoot} data-embedded={embedded ? "true" : "false"}>
      {/* ── Desktop horizontal layout ── */}
      <Box className={sxStyles.sx5}>
        <Box className={sxStyles.sx6}>
          {steps.map((step, idx) => {
            const nodeStatus = getNodeStatus(idx, progressState, isCancelled);
            const lineToNext = idx < steps.length - 1;
            const isLineDone = progressState.highestIndex > idx && !isCancelled;
            const isCurrentErrorLine = progressState.isFailed && progressState.highestIndex === idx + 1;
            const isLastDoneLine = progressState.highestIndex === idx + 1 && !isCancelled;

            return (
              <Fragment key={step.key}>
                <NodeDot status={nodeStatus} />
                {lineToNext && (
                  <Box
                    className={sxStyles.progressLine}
                    data-status={isCurrentErrorLine ? "error" : isLineDone ? "success" : "wait"}
                  >
                    {isLineDone && !isCurrentErrorLine && (
                      <Box className={sxStyles.progressFill} data-last={isLastDoneLine ? "true" : undefined} />
                    )}
                  </Box>
                )}
              </Fragment>
            );
          })}
        </Box>

        {/* Desktop text labels */}
        <Box className={sxStyles.sx7}>
          {steps.map((step, idx) => {
            const nodeStatus = getNodeStatus(idx, progressState, isCancelled);
            const isDisabled = (progressState.isFailed || isCancelled) && progressState.highestIndex < idx;
            const isDone = progressState.highestIndex >= idx;
            const isActive = progressState.activeIndex === idx;
            const isError = progressState.isFailed && progressState.highestIndex === idx;
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
            const style = getNodeStyle(idx, steps.length);
            return (
              <Box
                key={step.key}
                className={sxStyles.desktopLabel}
                data-align={style.textAlign}
                style={{
                  "--oops-geometry-left": style.left,
                  "--oops-geometry-transform": style.transform,
                } as React.CSSProperties}
              >
                <Text className={sxStyles.desktopTitle} data-status={nodeStatus} data-disabled={isDisabled ? "true" : undefined}>
                  {step.title}
                </Text>
                <Text className={sxStyles.desktopSubtitle}>
                  {subtitle}
                </Text>
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* ── Mobile vertical layout ── */}
      <Box className={sxStyles.sx8}>
        {steps.map((step, idx) => {
          const nodeStatus = getNodeStatus(idx, progressState, isCancelled);
          const isDisabled = (progressState.isFailed || isCancelled) && progressState.highestIndex < idx;
          const isDone = progressState.highestIndex >= idx;
          const isActive = progressState.activeIndex === idx;
          const isError = progressState.isFailed && progressState.highestIndex === idx;
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
          const isLast = idx === steps.length - 1;
          const isLineDone = progressState.highestIndex > idx && !isCancelled;
          const isCurrentErrorLine = progressState.isFailed && progressState.highestIndex === idx + 1;

          return (
            <Box key={step.key} className={sxStyles.sx9}>
              {/* Left rail: dot + vertical line */}
              <Box className={sxStyles.sx10}>
                <NodeDot status={nodeStatus} />
                {!isLast && (
                  <Box
                    className={sxStyles.mobileLine}
                    data-status={isCurrentErrorLine ? "error" : isLineDone ? "success" : "wait"}
                  />
                )}
              </Box>
              {/* Right: text */}
              <Box className={sxStyles.mobileContent} data-last={isLast ? "true" : undefined}>
                <Text className={sxStyles.mobileTitle} data-status={nodeStatus} data-disabled={isDisabled ? "true" : undefined}>
                  {step.title}
                </Text>
                <Text className={sxStyles.mobileSubtitle}>
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
