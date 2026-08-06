"use client";

import { Trash2 } from "lucide-react";
import React from "react";
import { Button, Checkbox, Text } from "@/components/ui/primitives";
import { Group, Modal, Stack } from "@mantine/core";
import type { BatchDeleteSelection } from "../api";

type Props = {
  opened: boolean;
  filename: string;
  taskCount: number;
  sourceAvailable: boolean;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: (selection: BatchDeleteSelection) => void | Promise<void>;
};

const DEFAULT_SELECTION: BatchDeleteSelection = {
  source: false,
  selection_records: true,
  tasks: false,
};

export function BatchDeleteDialog({
  opened,
  filename,
  taskCount,
  sourceAvailable,
  loading = false,
  onCancel,
  onConfirm,
}: Props) {
  const [selection, setSelection] = React.useState(DEFAULT_SELECTION);

  const update = (key: keyof BatchDeleteSelection) => (event: React.ChangeEvent<HTMLInputElement>) => {
    const checked = event.currentTarget.checked;
    setSelection((current) => ({ ...current, [key]: checked }));
  };
  const canConfirm = !loading && Object.values(selection).some(Boolean);
  const cancel = () => {
    setSelection(DEFAULT_SELECTION);
    onCancel();
  };
  const confirm = async () => {
    await onConfirm(selection);
    setSelection(DEFAULT_SELECTION);
  };

  return (
    <Modal
      opened={opened}
      onClose={cancel}
      title="删除批量扫描内容"
      centered
      closeOnClickOutside={!loading}
      closeOnEscape={!loading}
      withCloseButton={!loading}
    >
      <Text size="sm" className="batch-delete-dialog__filename">{filename}</Text>
      <Stack gap="md">
        <Checkbox
          label="源 PDF"
          checked={selection.source}
          disabled={!sourceAvailable || loading}
          onChange={update("source")}
        />
        <Text size="xs" className="batch-delete-dialog__description">删除原始文件；之后重新导入相同内容即可恢复。</Text>
        <Checkbox
          label="选框记录"
          checked={selection.selection_records}
          disabled={loading}
          onChange={update("selection_records")}
        />
        <Text size="xs" className="batch-delete-dialog__description">删除批量扫描的裁剪、分栏和题框记录。</Text>
        <Checkbox
          label={`题目任务（${taskCount}）`}
          checked={selection.tasks}
          disabled={!taskCount || loading}
          onChange={update("tasks")}
        />
        <Text size="xs" className="batch-delete-dialog__description">删除已提交的题目任务及其题目内容。</Text>
      </Stack>
      <Group justify="flex-end" mt="xl">
        <Button variant="default" onClick={cancel} disabled={loading}>取消</Button>
        <Button
          variant="danger"
          leadingVisual={Trash2}
          onClick={() => void confirm()}
          disabled={!canConfirm}
        >
          {loading ? "删除中…" : "删除所选内容"}
        </Button>
      </Group>
    </Modal>
  );
}
