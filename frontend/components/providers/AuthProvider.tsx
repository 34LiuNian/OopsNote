"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { beginSignin, beginSignout, currentUser, hasAccessToken, refreshCurrentUser, type AuthUser } from "@/lib/auth";

type AuthContextValue = {
  authenticated: boolean;
  loading: boolean;
  user: AuthUser | null;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue>({
  authenticated: false,
  loading: true,
  user: null,
  signOut: () => undefined,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isCallback = pathname === "/auth/callback";
  const initialAuthenticated = !isCallback && hasAccessToken();
  const [loading, setLoading] = useState(!isCallback && !initialAuthenticated);
  const [authenticated, setAuthenticated] = useState(initialAuthenticated);
  const [user, setUser] = useState<AuthUser | null>(() => initialAuthenticated ? currentUser() : null);

  useEffect(() => {
    if (isCallback || authenticated) return;
    void beginSignin(pathname).catch(() => undefined);
  }, [authenticated, isCallback, pathname]);

  useEffect(() => {
    if (!authenticated || user) return;
    void refreshCurrentUser().then(setUser).catch((error: unknown) => {
      console.warn("Unable to load the current OIDC user", error);
    });
  }, [authenticated, user]);

  const value = useMemo<AuthContextValue>(() => ({
    authenticated,
    loading,
    user,
    signOut: () => {
      setAuthenticated(false);
      setLoading(true);
      setUser(null);
      void Promise.resolve().then(beginSignout);
    },
  }), [authenticated, loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
