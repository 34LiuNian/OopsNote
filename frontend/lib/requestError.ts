import { notify } from "./notify";
import { requestErrorMessage } from "./notificationPolicy";

export { requestErrorMessage };

export function notifyRequestError(title: string, reason: unknown, fallback?: string): string {
  const description = requestErrorMessage(reason, fallback ?? title);
  notify.error({ title, description });
  return description;
}
