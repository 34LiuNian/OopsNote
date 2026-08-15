"use client";

export { isBetterAuthMode, isLocalAuthMode } from "./auth-mode";

export type AuthUser = {
  subject: string;
  displayName: string;
  email: string | null;
  picture: string | null;
  roles: string[];
};

export const LOCAL_USER: AuthUser = {
  subject: "local-admin",
  displayName: "本地管理员",
  email: null,
  picture: null,
  roles: ["admin"],
};

export function isAdminUser(user: AuthUser | null): boolean {
  return Boolean(user?.roles.includes("admin"));
}
