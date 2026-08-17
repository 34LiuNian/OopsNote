import type { ApiErrorCategory } from "../types/api";

export type ApiErrorPayload = {
  category: ApiErrorCategory;
  code: string;
  message: string;
  retryable: boolean;
  scope: string;
  task_id?: string;
  run_id?: string;
  diagram_item_id?: string;
  details?: Record<string, unknown>;
};

export class ApiError extends Error {
  readonly status: number;
  readonly payload?: ApiErrorPayload;

  constructor(message: string, status: number, payload?: ApiErrorPayload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function apiErrorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.payload?.code ?? null : null;
}

export function hasApiErrorCode(error: unknown, ...codes: string[]): boolean {
  const code = apiErrorCode(error);
  return code !== null && codes.includes(code);
}

export function isRetryableApiError(error: unknown): boolean {
  return error instanceof ApiError && error.payload?.retryable === true;
}
