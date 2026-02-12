"use client";

import { Box, Button, Label } from "@primer/react";
import { SyncIcon } from "@primer/octicons-react";

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

export function TaskActions({
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
    <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}>
      {status && <Label variant="secondary">状态：{status}</Label>}
      {(status === "pending" || status === "processing") && (
        <Button variant="danger" onClick={onCancel} disabled={isCancelling || isLoading}>
          {isCancelling ? "作废中..." : "停止并作废"}
        </Button>
      )}
      {(status === "failed" || status === "completed") && (
        <Button onClick={onRetry} disabled={isRetrying || isLoading || isCancelling} leadingVisual={SyncIcon}>
          {isRetrying ? "重试中..." : "重试"}
        </Button>
      )}
      <Button onClick={onRefresh} disabled={isLoading} leadingVisual={SyncIcon}>
        {isLoading ? "刷新中..." : "查看最新状态"}
      </Button>
      <Button variant="danger" onClick={onDelete} disabled={isLoading || isCancelling}>
        删除任务
      </Button>
    </Box>
  );
}
