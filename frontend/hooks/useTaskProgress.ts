import { useMemo } from "react";

export type ProgressStepKey =
  | "queued"
  | "ocr"
  | "solving"
  | "tagging"
  | "diagram_generating"
  | "diagram_rendering"
  | "diagram_reviewing";

export type ProgressStep = { key: ProgressStepKey; title: string };

export const PROGRESS_STEPS: ProgressStep[] = [
  { key: "queued", title: "入队" },
  { key: "ocr", title: "OCR 识别" },
  { key: "solving", title: "题解" },
  { key: "tagging", title: "打标" },
];

export const DIAGRAM_PROGRESS_STEPS: ProgressStep[] = [
  { key: "queued", title: "入队" },
  { key: "diagram_generating", title: "生成" },
  { key: "diagram_rendering", title: "渲染" },
  { key: "diagram_reviewing", title: "视觉复核" },
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

  // Diagram reconstruction stages belong to the independent diagram track.
  if (lower === "generate" || lower === "generating" || lower === "diagram_generating") {
    return "diagram_generating";
  }
  if (lower === "render" || lower === "rendering" || lower === "diagram_rendering") {
    return "diagram_rendering";
  }
  if (lower === "review" || lower === "reviewing" || lower === "diagram_reviewing") {
    return "diagram_reviewing";
  }

  if (
    lower === "diagramming" ||
    lower === "diagram" ||
    lower.includes("diagram") ||
    raw.includes("图形重建") ||
    raw.includes("重建图形")
  ) {
    return "diagram_generating";
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
  steps?: ProgressStep[];
}

export interface UseTaskProgressResult {
  isRunning: boolean;
  isCompleted: boolean;
  isFailed: boolean;
  isCancelled: boolean;
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
  steps = PROGRESS_STEPS,
}: UseTaskProgressOptions): UseTaskProgressResult {
  return useMemo(() => {
    const taskStatus = status ?? "pending";
    const isRunning = taskStatus === "pending" || taskStatus === "processing";
    const isCompleted = taskStatus === "completed";
    const isFailed = taskStatus === "failed";
    const isCancelled = taskStatus === "cancelled";

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
      const idx = steps.findIndex((s) => s.key === step);
      if (idx > highestIndex) highestIndex = idx;
    }

    let activeIndex = highestIndex;
    if (isCompleted || isCancelled) {
      highestIndex = steps.length - 1;
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
      isCancelled,
      highestIndex,
      activeIndex,
      latestLine,
    };
  }, [stage, stageMessage, status, statusMessage, steps, streamProgress]);
}
