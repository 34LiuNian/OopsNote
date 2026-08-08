export type NotificationAutoClose = number | false | undefined;

function hash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

export function notificationAutoClose(
  color: string,
  requested: NotificationAutoClose,
): NotificationAutoClose {
  return color === "red" ? false : requested;
}

export function errorNotificationId(
  title: string,
  description?: string,
  explicitId?: string,
): string {
  if (explicitId) return explicitId;
  const evidence = (description || title).trim().replace(/\s+/g, " ");
  return `error-${hash(evidence || "unknown-error")}`;
}
