"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { AuthStatusScreen } from "./AuthStatusScreen";
import AppLayout from "@/components/layout/AppLayout";

export function AuthBoundary({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { authenticated, error, loading } = useAuth();
  if (
    pathname === "/auth/callback"
    || pathname === "/login"
    || pathname === "/register"
    || pathname === "/invite"
    || pathname === "/setup"
  ) return <>{children}</>;
  if (loading || !authenticated) return <AuthStatusScreen phase="signin" error={error} />;
  return <AppLayout>{children}</AppLayout>;
}
