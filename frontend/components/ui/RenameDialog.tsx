"use client";

import { Button, Group, Modal, TextInput } from "@mantine/core";

type RenameDialogProps = {
  opened: boolean;
  title: string;
  label?: string;
  value: string;
  onChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
  confirmLabel?: string;
  loading?: boolean;
};

export function RenameDialog({
  opened,
  title,
  label = "名称",
  value,
  onChange,
  onCancel,
  onConfirm,
  confirmLabel = "保存",
  loading = false,
}: RenameDialogProps) {
  const canConfirm = value.trim().length > 0 && !loading;

  return (
    <Modal
      opened={opened}
      onClose={onCancel}
      title={title}
      centered
      closeOnClickOutside={!loading}
      closeOnEscape={!loading}
      withCloseButton={!loading}
    >
      <TextInput
        autoFocus
        label={label}
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && canConfirm) {
            event.preventDefault();
            void onConfirm();
          }
        }}
      />
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onCancel} disabled={loading}>取消</Button>
        <Button onClick={() => void onConfirm()} disabled={!canConfirm} loading={loading}>
          {confirmLabel}
        </Button>
      </Group>
    </Modal>
  );
}
