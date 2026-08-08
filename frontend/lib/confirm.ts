import type { ReactNode } from "react";
import { modals } from "@/components/ui/primitives";
import { formatApiError } from "@/lib/errorFormatter";
import { notify } from "@/lib/notify";

type ConfirmActionOptions = {
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
};

export function confirmAction({
  title,
  message,
  confirmLabel = "确认",
  destructive = false,
  onConfirm,
}: ConfirmActionOptions) {
  modals.openConfirmModal({
    title,
    children: message,
    labels: { cancel: "取消", confirm: confirmLabel },
    confirmProps: destructive ? { color: "red" } : undefined,
    onConfirm: () => {
      void (async () => {
        try {
          await onConfirm();
        } catch (error) {
          notify.error({
            title: "操作失败",
            description: formatApiError(error),
          });
        }
      })();
    },
  });
}
