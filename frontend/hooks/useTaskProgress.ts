import { useMemo } from "react";

export type ProgressStepKey = "queued" | "ocr" | "solving" | "tagging";

export const PROGRESS_STEPS: Array<{ key: ProgressStepKey; title: string }> = [
  { key: "queued", title: "入队" },
  { key: "ocr", title: "OCR 识别" },
  { key: "solving", title: "题解" },
  { key: "tagging", title: "打标" },
];

export function inferStepFromText(text: string): ProgressStepKey | null {
  const raw = String(text || "").trim();
  if (!raw) return null;
  const lower = raw.toLowerCase();

  // queued/starting stage
  if (
    lower === "starting" ||
    lower.includes("retry") ||
    lower.includes("queue") ||
    lower.includes("pending") ||
    raw.includes("入队") ||
    raw.includes("等待处理") ||
    raw.includes("开始处理")
  ) {
    return "queued";
  }

  // OCR/extracting stage
  if (
    lower === "extracting" ||
    lower === "ocr" ||
    lower.includes("extract") ||
    lower.includes("ocr") ||
    raw.includes("识别") ||
    raw.includes("提取")
  ) {
    return "ocr";
  }

  // Solving stage
  if (
    lower === "solving" ||
    lower === "solve" ||
    lower.includes("solv") ||
    raw.includes("解题") ||
    raw.includes("题解")
  ) {
    return "solving";
  }

  // Tagging/archiving stage
  if (
    lower === "tagging" ||
    lower === "tag" ||
    lower === "archiving" ||
    lower === "archive" ||
    lower === "done" ||
    lower.includes("tag") ||
    lower.includes("archiv") ||
    raw.includes("标注") ||
    raw.includes("打标") ||
    raw.includes("归档") ||
    raw.includes("完成")
  ) {
    return "tagging";
  }

  return null;
}

export interface UseTaskProgressOptions {
  status?: string | null;
  stage?: string | null;
  stageMessage?: string | null;
  statusMessage?: string | null;
  streamProgress?: string[];
}

export interface UseTaskProgressResult {
  isRunning: boolean;
  isCompleted: boolean;
  isFailed: boolean;
  highestIndex: number;
  activeIndex: number;
  latestLine: string;
}

export function useTaskProgress({
  status,
  stage,
  stageMessage,
  statusMessage,
  streamProgress = [],
}: UseTaskProgressOptions): UseTaskProgressResult {
  return useMemo(() => {
    const taskStatus = status ?? "pending";
    const isRunning = taskStatus === "pending" || taskStatus === "processing";
    const isCompleted = taskStatus === "completed";
    const isFailed = taskStatus === "failed";

    const observed: ProgressStepKey[] = [];
    const pushStep = (candidate: string | null | undefined) => {
      if (!candidate) return;
      const mapped = inferStepFromText(candidate);
      if (mapped) observed.push(mapped);
    };

    pushStep(stage ?? null);
    pushStep(stageMessage ?? null);
    pushStep(statusMessage);
    streamProgress.forEach(pushStep);

    let highestIndex = 0;
    for (const step of observed) {
      const idx = PROGRESS_STEPS.findIndex((s) => s.key === step);
      if (idx > highestIndex) highestIndex = idx;
    }

    let activeIndex = highestIndex;
    if (isCompleted) {
      highestIndex = PROGRESS_STEPS.length - 1;
      activeIndex = -1;
    } else if (!isRunning) {
      activeIndex = -1;
    } else if (observed.length === 0) {
      // 初始状态：任务刚创建，尚未有任何进度时，第一步设为进行中
      highestIndex = -1;
      activeIndex = 0;
    }

    const latestLine =
      streamProgress.length > 0
        ? streamProgress[streamProgress.length - 1]
        : statusMessage || stageMessage || "等待处理";

    return {
      isRunning,
      isCompleted,
      isFailed,
      highestIndex,
      activeIndex,
      latestLine,
    };
  }, [status, stage, stageMessage, statusMessage, streamProgress]);
}
