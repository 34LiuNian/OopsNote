"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { AuthStatusScreen } from "./AuthStatusScreen";

export function AuthBoundary({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { authenticated, error, loading } = useAuth();
  if (pathname === "/auth/callback" || pathname === "/login" || pathname === "/invite") return <>{children}</>;
  if (loading || !authenticated) return <AuthStatusScreen phase="signin" error={error} />;
  return <>{children}</>;
}
