"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { beginSignin, beginSignout, currentUser, hasAccessToken, isLocalAuthMode, refreshCurrentUser, type AuthUser } from "@/lib/auth";

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
  const isCallback = pathname === "/auth/callback";
  const initialAuthenticated = !isCallback && hasAccessToken();
  const [loading, setLoading] = useState(!isCallback && !initialAuthenticated);
  const [authenticated, setAuthenticated] = useState(initialAuthenticated);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(() => initialAuthenticated ? currentUser() : null);
  const signinStarted = useRef(false);

  useEffect(() => {
    if (isLocalAuthMode() || isCallback || authenticated || signinStarted.current) return;
    signinStarted.current = true;
    void beginSignin(pathname).catch((reason: unknown) => {
      const message = reason instanceof Error ? reason.message : "无法启动 OIDC 登录";
      console.error("Unable to start OIDC sign-in", reason);
      setError(message);
      setLoading(false);
    });
  }, [authenticated, isCallback, pathname]);

  useEffect(() => {
    if (isLocalAuthMode() || !authenticated || user) return;
    void refreshCurrentUser().then(setUser).catch((error: unknown) => {
      console.warn("Unable to load the current OIDC user", error);
    });
  }, [authenticated, user]);

  const value = useMemo<AuthContextValue>(() => ({
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
  }), [authenticated, error, loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
