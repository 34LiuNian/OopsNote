// Use /api proxy to avoid CORS issues
export const API_BASE = "/api";

import { accessTokenOrRedirect } from "./auth";
import type { ApiErrorCategory } from "../types/api";

function directBackendBase(): string | null {
  const configured = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (process.env.NODE_ENV !== "development" || typeof window === "undefined") return null;
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export type ApiRequestInit = RequestInit & {
  skipAuth?: boolean;
};

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
  constructor(
    message: string,
    readonly status: number,
    readonly payload?: ApiErrorPayload,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function apiErrorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.payload?.code ?? null : null;
}

export function hasApiErrorCode(error: unknown, ...codes: string[]): boolean {
  const code = apiErrorCode(error);
  return code !== null && codes.includes(code);
}

async function requestBackend(input: RequestInfo | URL, init: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError("无法连接后端服务", 0, {
      category: "request",
      code: "backend_unreachable",
      message: "无法连接后端服务",
      retryable: true,
      scope: "transport",
    });
  }
}

function isApiErrorPayload(value: unknown): value is ApiErrorPayload {
  if (!value || typeof value !== "object") return false;
  const payload = value as Partial<ApiErrorPayload>;
  return (
    typeof payload.category === "string" &&
    typeof payload.code === "string" &&
    typeof payload.message === "string" &&
    typeof payload.retryable === "boolean" &&
    typeof payload.scope === "string"
  );
}

function parseErrorResponse(
  rawText: string,
  status: number,
): { message: string; payload?: ApiErrorPayload } {
  if (rawText) {
    try {
      const parsed = JSON.parse(rawText) as { detail?: unknown };
      if (isApiErrorPayload(parsed?.detail)) {
        return { message: parsed.detail.message, payload: parsed.detail };
      }
      if (typeof parsed?.detail === "string") return { message: parsed.detail };
      if (parsed?.detail && typeof parsed.detail === "object") {
        const message = (parsed.detail as { message?: unknown }).message;
        return { message: typeof message === "string" ? message : rawText };
      }
    } catch {
      if (/^\s*<(!doctype\s+html|html)\b/i.test(rawText)) {
        return { message: `服务返回了无效响应（${status}）` };
      }
    }
  }
  if (status === 413) return { message: "上传内容超过服务允许的大小，请压缩或拆分文件后重试" };
  if (!rawText) return { message: `请求失败：${status}` };
  return { message: rawText };
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const parsed = parseErrorResponse(await response.text(), response.status);
  return new ApiError(parsed.message, response.status, parsed.payload);
}

export async function fetchApi(path: string, init?: ApiRequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (!init?.skipAuth) {
    const token = await accessTokenOrRedirect();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  return requestBackend(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
}

// Large raw files bypass the Next development rewrite, which otherwise buffers
// the request before forwarding it to FastAPI.
export async function fetchRawUpload(path: string, init?: ApiRequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (!init?.skipAuth) {
    const token = await accessTokenOrRedirect();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  const base = directBackendBase() ?? API_BASE;
  return requestBackend(`${base}${path}`, {
    ...init,
    headers,
  });
}

export async function fetchJson<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetchApi(path, {
    ...init,
    headers,
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }

  return (await response.json()) as T;
}
