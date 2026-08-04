import { Button } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { createElement } from "react";
import type { ComponentType, ReactNode } from "react";

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

function show(color: string, { description, button, ...options }: NotifyOptions) {
  return notifications.show({ ...options, color, message: messageContent(description, button) });
}

export const notify = {
  success: (options: NotifyOptions) => show("green", options),
  error: (options: NotifyOptions) => show("red", options),
  warning: (options: NotifyOptions) => show("yellow", options),
  info: (options: NotifyOptions) => show("blue", options),
  update: ({ color = "blue", description, button, ...options }: NotifyOptions & { color?: string }) => notifications.update({
    ...options,
    color,
    message: messageContent(description, button),
  }),
  dismiss: (id: string) => notifications.hide(id),
};
