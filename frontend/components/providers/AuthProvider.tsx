"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { authClient } from "@/lib/better-auth-client";
import { notify } from "@/lib/notify";
import {
  beginSignin,
  beginSignout,
  currentUser,
  hasAccessToken,
  isBetterAuthMode,
  isLocalAuthMode,
  refreshCurrentUser,
  type AuthUser,
} from "@/lib/auth";

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
  const isPublicAuthPage =
    pathname === "/login" || pathname === "/register" || pathname === "/invite" || pathname === "/setup";
  const betterAuthEnabled = isBetterAuthMode();
  const betterSession = authClient.useSession();
  const isCallback = pathname === "/auth/callback";
  const initialAuthenticated = !betterAuthEnabled && !isCallback && hasAccessToken();
  const [loading, setLoading] = useState(betterAuthEnabled || (!isCallback && !initialAuthenticated));
  const [authenticated, setAuthenticated] = useState(initialAuthenticated);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(() => initialAuthenticated ? currentUser() : null);
  const signinStarted = useRef(false);

  const sessionUser = betterSession.data?.user;
  const betterAuthUser = useMemo<AuthUser | null>(() => {
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
  }, [sessionUser]);

  useEffect(() => {
    if (!betterAuthEnabled || betterSession.isPending || betterAuthUser || isPublicAuthPage) return;
    if (signinStarted.current) return;
    signinStarted.current = true;
    void beginSignin(pathname + window.location.search);
  }, [betterAuthEnabled, betterAuthUser, betterSession.isPending, isPublicAuthPage, pathname]);

  useEffect(() => {
    if (betterAuthEnabled || isLocalAuthMode() || isCallback || authenticated || signinStarted.current) return;
    signinStarted.current = true;
    void beginSignin(pathname).catch((reason: unknown) => {
      const message = reason instanceof Error ? reason.message : "Unable to start OIDC sign-in";
      console.error("Unable to start OIDC sign-in", reason);
      setError(message);
      notify.error({ title: "无法开始登录", description: message });
      setLoading(false);
    });
  }, [authenticated, betterAuthEnabled, isCallback, pathname]);

  useEffect(() => {
    if (betterAuthEnabled || isLocalAuthMode() || !authenticated || user) return;
    void refreshCurrentUser().then(setUser).catch((reason: unknown) => {
      console.warn("Unable to load the current OIDC user", reason);
      notify.error({ title: "用户信息加载失败", description: reason instanceof Error ? reason.message : "无法读取当前用户信息" });
    });
  }, [authenticated, betterAuthEnabled, user]);

  const value = useMemo<AuthContextValue>(() => {
    if (betterAuthEnabled) {
      return {
        authenticated: Boolean(betterAuthUser),
        loading: betterSession.isPending || (!betterAuthUser && !isPublicAuthPage),
        error: betterSession.error?.message || null,
        user: betterAuthUser,
        signOut: () => {
          void authClient.signOut().then(() => window.location.assign("/login"));
        },
      };
    }
    return {
      authenticated,
      loading,
      error,
      user,
      signOut: () => {
        setAuthenticated(false);
        setLoading(true);
        setError(null);
        setUser(null);
        void Promise.resolve().then(beginSignout);
      },
    };
  }, [authenticated, betterAuthEnabled, betterAuthUser, betterSession.error, betterSession.isPending, error, isPublicAuthPage, loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
