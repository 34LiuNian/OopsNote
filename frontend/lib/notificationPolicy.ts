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

export function requestErrorMessage(reason: unknown, fallback: string): string {
  if (typeof reason === "string" && reason.trim()) return reason.trim();
  if (reason instanceof Error && reason.message.trim()) return reason.message;
  return fallback;
}

export function errorNotificationId(
  title: string,
  description?: string,
  explicitId?: string,
): string {
  if (explicitId) return explicitId;
  const titlePart = title.trim().replace(/\s+/g, " ");
  const descriptionPart = (description ?? "").trim().replace(/\s+/g, " ");
  const evidence = descriptionPart ? `${titlePart}\u0000${descriptionPart}` : titlePart;
  return `error-${hash(evidence || "unknown-error")}`;
}
