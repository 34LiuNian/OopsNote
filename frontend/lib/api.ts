import {
  clearAuthSession,
  getAccessToken,
  getRefreshToken,
  touchAuthActivity,
  updateSessionTokens,
} from "../features/auth/store";
import { refreshAccessToken } from "../features/auth/api";

// Use /api proxy to avoid CORS issues
export const API_BASE = "/api";

export type ApiRequestInit = RequestInit & {
  skipAuth?: boolean;
};

let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

function subscribeTokenRefresh(cb: (token: string) => void) {
  refreshSubscribers.push(cb);
}

function onTokenRefreshed(token: string) {
  refreshSubscribers.forEach(cb => cb(token));
  refreshSubscribers = [];
}

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

function withAuthHeaders(headers: Headers, skipAuth: boolean | undefined): Headers {
  if (skipAuth || typeof window === "undefined") {
    return headers;
  }
  touchAuthActivity();
  const token = getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function handle401(): Promise<string | null> {
  if (isRefreshing) {
    // Wait for ongoing refresh
    return new Promise(resolve => {
      subscribeTokenRefresh(token => resolve(token));
    });
  }

  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }

  isRefreshing = true;
  try {
    const response = await refreshAccessToken({ refresh_token: refreshToken });
    const newToken = response.access_token;
    
    // Update session with new token
    updateSessionTokens(newToken, response.expires_in);
    
    // Notify all waiting requests
    onTokenRefreshed(newToken);
    return newToken;
  } catch (error) {
    // Refresh failed, clear session
    clearAuthSession();
    return null;
  } finally {
    isRefreshing = false;
  }
}

export async function fetchApi(path: string, init?: ApiRequestInit): Promise<Response> {
  const headers = withAuthHeaders(new Headers(init?.headers), init?.skipAuth);

  let response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  // Handle 401 - try to refresh token
  if (response.status === 401 && !init?.skipAuth && typeof window !== "undefined") {
    const newToken = await handle401();
    
    if (newToken) {
      // Retry with new token
      headers.set("Authorization", `Bearer ${newToken}`);
      response = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers,
      });
    } else {
      // Refresh failed, redirect to login
      const currentPath = window.location.pathname + window.location.search;
      if (!window.location.pathname.startsWith("/login")) {
        const next = encodeURIComponent(currentPath || "/");
        window.location.assign(`/login?next=${next}`);
      }
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
