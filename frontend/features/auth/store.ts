"use client";

import type { UserPublic } from "../../types/api";

const AUTH_STORAGE_KEY = "oopsnote-auth-session";
const AUTH_CHANGE_EVENT = "oopsnote-auth-changed";

export type AuthSession = {
  accessToken: string;
  expiresAt: number;
  user: UserPublic;
};

function parseSession(raw: string | null): AuthSession | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AuthSession;
    if (!parsed?.accessToken || !parsed?.user?.username || !parsed?.user?.role) {
      return null;
    }
    if (typeof parsed.expiresAt !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}

function emitAuthChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
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
    clearAuthSession();
    return null;
  }
  return session?.accessToken ?? null;
}

export function getCurrentUser(): UserPublic | null {
  const session = getAuthSession();
  if (!isAuthSessionValid(session)) {
    clearAuthSession();
    return null;
  }
  return session?.user ?? null;
}

export function saveAuthSession(payload: {
  accessToken: string;
  expiresIn: number;
  user: UserPublic;
}): void {
  if (typeof window === "undefined") return;
  const expiresAt = Date.now() + Math.max(1, payload.expiresIn) * 1000;
  const session: AuthSession = {
    accessToken: payload.accessToken,
    expiresAt,
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

export function onAuthChanged(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const wrapped = () => listener();
  window.addEventListener(AUTH_CHANGE_EVENT, wrapped);
  return () => window.removeEventListener(AUTH_CHANGE_EVENT, wrapped);
}
