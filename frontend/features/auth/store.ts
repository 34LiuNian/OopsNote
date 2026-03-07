"use client";

import type { UserPublic } from "../../types/api";

const AUTH_STORAGE_KEY = "oopsnote-auth-session";
const AUTH_CHANGE_EVENT = "oopsnote-auth-changed";

export type AuthSession = {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  refreshExpiresAt: number;
  user: UserPublic;
};

function parseSession(raw: string | null): AuthSession | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AuthSession;
    if (
      !parsed?.accessToken ||
      !parsed?.refreshToken ||
      !parsed?.user?.username ||
      !parsed?.user?.role
    ) {
      return null;
    }
    if (typeof parsed.expiresAt !== "number" || typeof parsed.refreshExpiresAt !== "number") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function emitAuthChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

/** 静默清理（不触发事件），用于内部有效期检查路径，防止递归 */
function silentClear() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
}

export function getAuthSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  return parseSession(window.localStorage.getItem(AUTH_STORAGE_KEY));
}

export function isAuthSessionValid(session: AuthSession | null): boolean {
  if (!session) return false;
  return session.expiresAt > Date.now() + 5_000;
}

export function getAccessToken(): string | null {
  const session = getAuthSession();
  if (!isAuthSessionValid(session)) {
    // 用 silentClear 而非 clearAuthSession，避免触发事件→监听器→本函数的无限递归
    silentClear();
    return null;
  }
  return session?.accessToken ?? null;
}

export function getCurrentUser(): UserPublic | null {
  const session = getAuthSession();
  if (!isAuthSessionValid(session)) {
    // 同上，静默清理，不广播事件
    silentClear();
    return null;
  }
  return session?.user ?? null;
}

export function saveAuthSession(payload: {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  refreshExpiresIn: number;
  user: UserPublic;
}): void {
  if (typeof window === "undefined") return;
  const expiresAt = Date.now() + Math.max(1, payload.expiresIn) * 1000;
  const refreshExpiresAt = Date.now() + Math.max(1, payload.refreshExpiresIn) * 1000;
  const session: AuthSession = {
    accessToken: payload.accessToken,
    refreshToken: payload.refreshToken,
    expiresAt,
    refreshExpiresAt,
    user: payload.user,
  };
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
  emitAuthChanged();
}

export function clearAuthSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  emitAuthChanged();
}

export function updateSessionUser(user: UserPublic): void {
  if (typeof window === "undefined") return;
  const session = getAuthSession();
  if (!session) return;
  const next: AuthSession = {
    ...session,
    user,
  };
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(next));
  emitAuthChanged();
}

export function updateSessionTokens(accessToken: string, expiresIn: number): void {
  if (typeof window === "undefined") return;
  const session = getAuthSession();
  if (!session) return;
  const expiresAt = Date.now() + Math.max(1, expiresIn) * 1000;
  const next: AuthSession = {
    ...session,
    accessToken,
    expiresAt,
  };
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(next));
  emitAuthChanged();
}

export function getRefreshToken(): string | null {
  const session = getAuthSession();
  if (!session) return null;
  if (session.refreshExpiresAt <= Date.now()) {
    silentClear();
    return null;
  }
  return session.refreshToken;
}

export function onAuthChanged(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const wrapped = () => listener();
  window.addEventListener(AUTH_CHANGE_EVENT, wrapped);
  return () => window.removeEventListener(AUTH_CHANGE_EVENT, wrapped);
}
