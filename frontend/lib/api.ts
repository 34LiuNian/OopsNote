// Use /api proxy to avoid CORS issues
export const API_BASE = "/api";

function directBackendBase(): string | null {
  const configured = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (process.env.NODE_ENV !== "development" || typeof window === "undefined") return null;
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export type ApiRequestInit = RequestInit & {
  skipAuth?: boolean;
};

function parseErrorMessage(rawText: string, status: number): string {
  if (!rawText) return `请求失败：${status}`;
  try {
    const parsed = JSON.parse(rawText) as { detail?: string | { message?: string } };
    if (typeof parsed?.detail === "string") return parsed.detail;
    if (parsed?.detail && typeof parsed.detail === "object") {
      return parsed.detail.message || rawText;
    }
  } catch {
    return rawText;
  }
  return rawText;
}

export async function fetchApi(path: string, init?: ApiRequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
}

// Large raw files bypass the Next development rewrite, which otherwise buffers
// the request before forwarding it to FastAPI.
export async function fetchRawUpload(path: string, init?: ApiRequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
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
    const errorText = await response.text();
    throw new Error(parseErrorMessage(errorText, response.status));
  }

  return (await response.json()) as T;
}
