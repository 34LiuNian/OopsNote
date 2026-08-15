"use client";

import { createContext, useContext, useEffect, useMemo, useRef } from "react";
import { usePathname } from "next/navigation";
import { authClient } from "@/lib/better-auth-client";
import { isLocalAuthMode, LOCAL_USER, type AuthUser } from "@/lib/auth";

type AuthContextValue = {
  authenticated: boolean;
  loading: boolean;
  error: string | null;
  user: AuthUser | null;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue>({
  authenticated: false,
  loading: true,
  error: null,
  user: null,
  signOut: () => undefined,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const localMode = isLocalAuthMode();
  const isPublicAuthPage =
    pathname === "/login" || pathname === "/register" || pathname === "/invite" || pathname === "/setup";
  const betterSession = authClient.useSession();
  const signinStarted = useRef(false);

  const sessionUser = betterSession.data?.user;
  const user = useMemo<AuthUser | null>(() => {
    if (localMode) return LOCAL_USER;
    if (!sessionUser) return null;
    const role = (sessionUser as typeof sessionUser & { role?: string | string[] | null }).role;
    return {
      subject: sessionUser.id,
      displayName: sessionUser.name || sessionUser.email || sessionUser.id,
      email: sessionUser.email || null,
      picture: sessionUser.image || null,
      roles: Array.isArray(role)
        ? role
        : typeof role === "string"
          ? role.split(",").map((item) => item.trim()).filter(Boolean)
          : [],
    };
  }, [localMode, sessionUser]);

  useEffect(() => {
    if (localMode || betterSession.isPending || user || isPublicAuthPage || signinStarted.current) return;
    signinStarted.current = true;
    const url = new URL("/login", window.location.origin);
    url.searchParams.set("returnTo", pathname + window.location.search);
    window.location.assign(url.toString());
  }, [betterSession.isPending, isPublicAuthPage, localMode, pathname, user]);

  const value = useMemo<AuthContextValue>(() => ({
    authenticated: Boolean(user),
    loading: localMode ? false : betterSession.isPending || (!user && !isPublicAuthPage),
    error: localMode ? null : betterSession.error?.message || null,
    user,
    signOut: () => {
      if (localMode) {
        window.location.reload();
        return;
      }
      void authClient.signOut().then(() => window.location.assign("/login"));
    },
  }), [betterSession.error, betterSession.isPending, isPublicAuthPage, localMode, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
