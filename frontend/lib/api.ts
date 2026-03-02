import { clearAuthSession, getAccessToken } from "../features/auth/store";

// Use /api proxy to avoid CORS issues
export const API_BASE = "/api";

export type ApiRequestInit = RequestInit & {
  skipAuth?: boolean;
};

function parseErrorMessage(rawText: string, status: number): string {
  if (!rawText) return `请求失败: ${status}`;
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

function withAuthHeaders(headers: Headers, skipAuth: boolean | undefined): Headers {
  if (skipAuth || typeof window === "undefined") {
    return headers;
  }
  const token = getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

export async function fetchApi(path: string, init?: ApiRequestInit): Promise<Response> {
  const headers = withAuthHeaders(new Headers(init?.headers), init?.skipAuth);

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (response.status === 401 && !init?.skipAuth && typeof window !== "undefined") {
    clearAuthSession();
    const currentPath = window.location.pathname + window.location.search;
    if (!window.location.pathname.startsWith("/login")) {
      const next = encodeURIComponent(currentPath || "/");
      window.location.assign(`/login?next=${next}`);
    }
  }

  return response;
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
