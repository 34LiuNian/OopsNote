"use client";

import { memo } from "react";
import { Box, Button, IconButton, Tooltip } from "@primer/react";
import { SyncIcon, TrashIcon, XCircleIcon } from "@primer/octicons-react";

type TaskActionsProps = {
  status?: string | null;
  isCancelling: boolean;
  isRetrying: boolean;
  isLoading: boolean;
  onCancel: () => void;
  onRetry: () => void;
  onRefresh: () => void;
  onDelete: () => void;
};

export const TaskActions = memo(function TaskActions({
  status,
  isCancelling,
  isRetrying,
  isLoading,
  onCancel,
  onRetry,
  onRefresh,
  onDelete,
}: TaskActionsProps) {
  return (
    <Box sx={{ display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" }}>
      {(status === "pending" || status === "processing") && (
        <Button
          variant="danger"
          size="small"
          onClick={onCancel}
          disabled={isCancelling || isLoading}
          leadingVisual={XCircleIcon}
        >
          {isCancelling ? "作废中..." : "停止"}
        </Button>
      )}
      {(status === "failed" || status === "completed" || status === "cancelled") && (
        <Button
          size="small"
          onClick={onRetry}
          disabled={isRetrying || isLoading || isCancelling}
          leadingVisual={SyncIcon}
        >
          {isRetrying ? "重试中..." : "重试"}
        </Button>
      )}
      <Tooltip text="刷新状态" direction="s">
        <IconButton
          icon={SyncIcon}
          aria-label="刷新状态"
          size="small"
          onClick={onRefresh}
          disabled={isLoading}
          variant="invisible"
        />
      </Tooltip>
      <Tooltip text="删除任务" direction="s">
        <IconButton
          icon={TrashIcon}
          aria-label="删除任务"
          size="small"
          onClick={onDelete}
          disabled={isLoading || isCancelling}
          variant="invisible"
          sx={{ color: "danger.fg" }}
        />
      </Tooltip>
    </Box>
  );
});
