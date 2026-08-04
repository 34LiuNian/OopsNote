// Use /api proxy to avoid CORS issues
export const API_BASE = "/api";

import { accessTokenOrRedirect } from "./auth";

function directBackendBase(): string | null {
  const configured = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (process.env.NODE_ENV !== "development" || typeof window === "undefined") return null;
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export type ApiRequestInit = RequestInit & {
  skipAuth?: boolean;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

function parseErrorMessage(rawText: string, status: number): string {
  if (rawText) {
    try {
      const parsed = JSON.parse(rawText) as { detail?: string | { message?: string } };
      if (typeof parsed?.detail === "string") return parsed.detail;
      if (parsed?.detail && typeof parsed.detail === "object") {
        return parsed.detail.message || rawText;
      }
    } catch {
      if (/^\s*<(!doctype\s+html|html)\b/i.test(rawText)) {
        return `服务返回了无效响应（${status}）`;
      }
    }
  }
  if (status === 413) return "上传内容超过服务允许的大小，请压缩或拆分文件后重试";
  if (!rawText) return `请求失败：${status}`;
  return rawText;
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  return new ApiError(
    parseErrorMessage(await response.text(), response.status),
    response.status,
  );
}

export async function fetchApi(path: string, init?: ApiRequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (!init?.skipAuth) {
    headers.set("Authorization", `Bearer ${await accessTokenOrRedirect()}`);
  }
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
}

// Large raw files bypass the Next development rewrite, which otherwise buffers
// the request before forwarding it to FastAPI.
export async function fetchRawUpload(path: string, init?: ApiRequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (!init?.skipAuth) {
    headers.set("Authorization", `Bearer ${await accessTokenOrRedirect()}`);
  }
  const base = directBackendBase() ?? API_BASE;
  return fetch(`${base}${path}`, {
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
