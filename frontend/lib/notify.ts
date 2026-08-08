import { Button } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { createElement } from "react";
import type { ComponentType, ReactNode } from "react";
import { errorNotificationId, notificationAutoClose } from "./notificationPolicy";

const NotificationButton = Button as unknown as ComponentType<{
  children?: ReactNode;
  onClick: () => void;
  size: "compact-xs";
  variant: "subtle";
}>;

type NotificationPosition = "top-left" | "top-right" | "top-center" | "bottom-left" | "bottom-right" | "bottom-center";

type NotifyOptions = {
  title: string;
  description?: string;
  message?: ReactNode;
  id?: string;
  position?: NotificationPosition;
  autoClose?: number | false;
  button?: {
    title: string;
    onClick: () => void;
  };
};

function messageContent(description: string | undefined, button: NotifyOptions["button"]) {
  if (!button) return description ?? "";
  return createElement(
    "div",
    { style: { display: "flex", alignItems: "center", gap: "8px", justifyContent: "space-between" } },
    description ? createElement("span", null, description) : null,
    createElement(NotificationButton, { size: "compact-xs", variant: "subtle", onClick: button.onClick }, button.title),
  );
}

function resolvedMessage(description: string | undefined, button: NotifyOptions["button"], message: ReactNode) {
  return message ?? messageContent(description, button);
}

function show(color: string, { description, button, message, autoClose, ...options }: NotifyOptions) {
  const id = color === "red"
    ? errorNotificationId(options.title, description, options.id)
    : options.id;
  const notification = {
    ...options,
    id,
    color,
    autoClose: notificationAutoClose(color, autoClose),
    priority: color === "red" ? 100 : 0,
    message: resolvedMessage(description, button, message),
  };
  if (id) {
    notifications.show(notification);
    notifications.update(notification);
    return id;
  }
  return notifications.show(notification);
}

export const notify = {
  success: (options: NotifyOptions) => show("green", options),
  error: (options: NotifyOptions) => show("red", options),
  warning: (options: NotifyOptions) => show("yellow", options),
  info: (options: NotifyOptions) => show("blue", options),
  update: ({ color = "blue", description, button, message, autoClose, ...options }: NotifyOptions & { color?: string }) => {
    const id = color === "red"
      ? errorNotificationId(options.title, description, options.id)
      : options.id;
    return notifications.update({
      ...options,
      id,
      color,
      autoClose: notificationAutoClose(color, autoClose),
      priority: color === "red" ? 100 : 0,
      message: resolvedMessage(description, button, message),
    });
  },
  upsert: ({ color = "blue", ...options }: NotifyOptions & { color?: string }) => {
    const id = show(color, options);
    notifications.update({
      ...options,
      id,
      color,
      autoClose: notificationAutoClose(color, options.autoClose),
      priority: color === "red" ? 100 : 0,
      message: resolvedMessage(options.description, options.button, options.message),
    });
    return id;
  },
  dismiss: (id: string) => notifications.hide(id),
};
