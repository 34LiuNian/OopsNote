"use client";

import { useEffect } from "react";
import { notify } from "@/lib/notify";
import { errorNotificationId } from "@/lib/notificationPolicy";

export function useRenderErrorNotification(title: string, message: string) {
  useEffect(() => {
    const description = message.trim();
    if (!description) return;
    const id = errorNotificationId(title, description);
    notify.error({ title, description, id });
    return () => {
      notify.dismiss(id);
    };
  }, [title, message]);
}
