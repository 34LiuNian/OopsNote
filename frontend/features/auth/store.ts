"use client";

import type { UserPublic } from "../../types/api";

const AUTH_STORAGE_KEY = "oopsnote-auth-session";
const AUTH_CHANGE_EVENT = "oopsnote-auth-changed";

export type AuthSession = {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  refreshExpiresAt: number;
  sessionStartedAt: number;
  lastActivityAt: number;
  user: UserPublic;
};

const EXPIRY_SKEW_MS = 5_000;
const INACTIVITY_TIMEOUT_MS = 30 * 60 * 1000;
const SESSION_MAX_AGE_MS = 2 * 24 * 60 * 60 * 1000;

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
    const now = Date.now();
    const sessionStartedAt =
      typeof parsed.sessionStartedAt === "number" ? parsed.sessionStartedAt : now;
    const lastActivityAt =
      typeof parsed.lastActivityAt === "number" ? parsed.lastActivityAt : sessionStartedAt;
    return {
      ...parsed,
      sessionStartedAt,
      lastActivityAt,
    };
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
  return session.expiresAt > Date.now() + EXPIRY_SKEW_MS;
}

function isRefreshTokenValid(session: AuthSession | null): boolean {
  if (!session) return false;
  return session.refreshExpiresAt > Date.now() + EXPIRY_SKEW_MS;
}

function isSessionWithinPolicy(session: AuthSession | null): boolean {
  if (!session) return false;
  const now = Date.now();
  if (now - session.lastActivityAt > INACTIVITY_TIMEOUT_MS) {
    return false;
  }
  if (now - session.sessionStartedAt > SESSION_MAX_AGE_MS) {
    return false;
  }
  return true;
}

function getSessionIfPolicyValid(): AuthSession | null {
  const session = getAuthSession();
  if (!session) {
    return null;
  }
  if (!isSessionWithinPolicy(session)) {
    silentClear();
    return null;
  }
  return session;
}

export function getAccessToken(): string | null {
  const session = getSessionIfPolicyValid();
  if (!session) {
    return null;
  }
  if (!isAuthSessionValid(session)) {
    // access token 过期时保留 refresh token，交给请求层自动续期
    if (!isRefreshTokenValid(session)) {
      // 仅当 refresh token 也失效时才清理
      silentClear();
    }
    return null;
  }
  return session.accessToken;
}

export function getCurrentUser(): UserPublic | null {
  const session = getSessionIfPolicyValid();
  if (!session) {
    return null;
  }
  if (!isRefreshTokenValid(session)) {
    // refresh token 已失效，判定为真正登出
    silentClear();
    return null;
  }
  return session.user;
}

export function saveAuthSession(payload: {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  refreshExpiresIn: number;
  user: UserPublic;
}): void {
  if (typeof window === "undefined") return;
  const now = Date.now();
  const expiresAt = now + Math.max(1, payload.expiresIn) * 1000;
  const refreshExpiresAt = now + Math.max(1, payload.refreshExpiresIn) * 1000;
  const session: AuthSession = {
    accessToken: payload.accessToken,
    refreshToken: payload.refreshToken,
    expiresAt,
    refreshExpiresAt,
    sessionStartedAt: now,
    lastActivityAt: now,
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
  const session = getSessionIfPolicyValid();
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
  const session = getSessionIfPolicyValid();
  if (!session) return null;
  if (!isRefreshTokenValid(session)) {
    silentClear();
    return null;
  }
  return session.refreshToken;
}

export function touchAuthActivity(): void {
  if (typeof window === "undefined") return;
  const session = getSessionIfPolicyValid();
  if (!session) return;
  const now = Date.now();
  if (now - session.lastActivityAt < 1000) return;
  const next: AuthSession = {
    ...session,
    lastActivityAt: now,
  };
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(next));
}

export function onAuthChanged(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const wrapped = () => listener();
  window.addEventListener(AUTH_CHANGE_EVENT, wrapped);
  return () => window.removeEventListener(AUTH_CHANGE_EVENT, wrapped);
}
