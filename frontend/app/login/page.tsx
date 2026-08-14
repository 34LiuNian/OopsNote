"use client";

import { FormEvent, useEffect, useState } from "react";
import { KeyRound, LoaderCircle, LogIn, UserRound } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import styles from "@/components/auth/AuthenticationShell.module.css";
import { authClient } from "@/lib/better-auth-client";

export default function LoginPage() {
  const [identifier, setIdentifier] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URL(window.location.href).searchParams.get("identifier") || "";
  });
  const [password, setPassword] = useState("");
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [setupAvailable, setSetupAvailable] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void authClient.$fetch<{ mode: "closed" | "invite" | "open" }>("/registration-policy").then((result) => {
      if (result.data) setRegistrationOpen(result.data.mode !== "closed");
    }).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "无法读取注册策略");
    });
    void fetch("/api/admin/setup").then((response) => {
      if (!response.ok) return null;
      return response.json() as Promise<{ available: boolean }>;
    }).then((payload) => {
      if (payload?.available) setSetupAvailable(true);
    }).catch(() => {});
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const returnTo = new URL(window.location.href).searchParams.get("returnTo") || "/library";
      const value = identifier.trim();
      const result = value.includes("@")
        ? await authClient.signIn.email({ email: value, password })
        : await authClient.signIn.username({ username: value, password });
      if (result.error) {
        setError(result.error.message || "用户名、邮箱或密码不正确");
        return;
      }
      window.location.replace(returnTo.startsWith("/") ? returnTo : "/library");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录请求失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthenticationShell title="登录 OopsNote" description="进入你的独立题库。">
      <ErrorBanner message={error ?? ""} title="登录失败" />
      <form className={styles.form} onSubmit={submit}>
        <label className={styles.field}>
          用户名或邮箱
          <div className={styles.input}>
            <UserRound size={18} aria-hidden="true" />
            <input type="text" autoComplete="username" value={identifier} onChange={(event) => setIdentifier(event.target.value)} required />
          </div>
        </label>
        <label className={styles.field}>
          密码
          <div className={styles.input}>
            <KeyRound size={18} aria-hidden="true" />
            <input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} required />
          </div>
        </label>
        <div className={styles.footer}>
          {registrationOpen ? <Link className={styles.back} href="/register">创建账号</Link> : <span />}
          <Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : LogIn} disabled={submitting}>
            {submitting ? "正在登录" : "登录"}
          </Button>
        </div>
        {setupAvailable && (
          <div className={styles.footer}>
            <span className={styles.hint}>首次使用？</span>
            <Link className={styles.back} href="/setup">初始化管理员</Link>
          </div>
        )}
      </form>
    </AuthenticationShell>
  );
}
