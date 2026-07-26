"use client";

import { AlertTriangle, ExternalLink, RefreshCw } from "lucide-react";

import type { SelectionModel, SelectionReviewReason } from "@/components/batch-continuous";
import { Box, IconButton, Text } from "@/components/ui/primitives";
import { REVIEW_REASON_LABELS, selectionLocationLabel } from "./batchScanSupport";

type Props = {
  selections: SelectionModel[];
  activeSelectionId?: string;
  columnCount: number;
  onActivate: (selection: SelectionModel) => void;
  onReview: (selection: SelectionModel, reason: SelectionReviewReason | "") => void;
  onRetry: (selection: SelectionModel) => void;
};

export function BatchSelectionRail({ selections, activeSelectionId, columnCount, onActivate, onReview, onRetry }: Props) {
  return (
    <aside className="batch-selection-rail" aria-label="选框列表">
      <Box className="batch-selection-rail__header"><Text className="batch-rail-title">题目选框</Text><Text>{selections.length}</Text></Box>
      <div className="batch-selection-list">
        {selections.map((selection) => (
          <div key={selection.id} className={`batch-selection-list__item${selection.id === activeSelectionId ? " is-active" : ""}`}>
            <button type="button" className="batch-selection-list__primary" onClick={() => onActivate(selection)}>
              <span className={`batch-selection-list__number is-${selection.status}`}>{selection.questionNo}</span>
              <span>
                <strong>{selectionLocationLabel(selection, columnCount)}</strong>
                <small>{selection.status === "pending" ? "待提交" : selection.status === "processing" ? "处理中" : selection.status === "completed" ? "已完成" : selection.status === "needs_review" ? `需人工复核：${selection.reviewReason ? REVIEW_REASON_LABELS[selection.reviewReason] : "异常"}` : selection.error || "失败"}</small>
              </span>
            </button>
            <label className="batch-selection-list__review" title="标记或取消人工复核">
              <AlertTriangle size={14} aria-hidden="true" />
              <select aria-label={`第 ${selection.questionNo} 题异常状态`} value={selection.reviewReason ?? ""} onChange={(event) => onReview(selection, event.target.value as SelectionReviewReason | "")}>
                <option value="">无异常</option>
                {(Object.keys(REVIEW_REASON_LABELS) as SelectionReviewReason[]).map((reason) => (
                  <option key={reason} value={reason}>{REVIEW_REASON_LABELS[reason]}</option>
                ))}
              </select>
            </label>
            {(selection.status === "failed" || (selection.status === "needs_review" && selection.reviewPreviousStatus === "failed")) && selection.taskId && <IconButton icon={RefreshCw} size="small" variant="invisible" aria-label="重试" title="使用同一截图重试" onClick={() => onRetry(selection)} />}
            {(selection.status === "completed" || selection.status === "needs_review") && selection.taskId && <IconButton icon={ExternalLink} size="small" variant="invisible" aria-label="打开任务" title="打开任务" onClick={() => window.open(`/tasks/${selection.taskId}`, "_blank", "noopener,noreferrer")} />}
          </div>
        ))}
        {!selections.length && <Text className="batch-selection-list__empty">在页面上拖动以创建题目选框</Text>}
      </div>
    </aside>
  );
}
