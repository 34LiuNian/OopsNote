"use client";

import { FormEvent, useState } from "react";
import { KeyRound, LoaderCircle, Ticket, UserPlus } from "lucide-react";
import Link from "next/link";
import { authClient } from "@/lib/better-auth-client";
import { Button } from "@/components/ui/primitives";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import styles from "@/components/auth/AuthenticationShell.module.css";

function initialInvitationCode(): string {
  if (typeof window === "undefined") return "";
  return new URL(window.location.href).searchParams.get("token") || "";
}

export default function InvitePage() {
  const [invitationCode, setInvitationCode] = useState(initialInvitationCode);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function redeem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = invitationCode.trim();
    if (!token) {
      setError("请输入邀请码");
      return;
    }
    setSubmitting(true);
    setError(null);
    const result = await authClient.$fetch("/invite/redeem", { method: "POST", body: { token, password } });
    if (result.error) {
      setError(result.error.message || "邀请码无效或已过期");
      setSubmitting(false);
      return;
    }
    window.location.replace("/login?returnTo=/library");
  }

  return (
    <AuthenticationShell title="完成内测注册" description="输入管理员提供的邀请码，并设置一个登录密码。">
      <form className={styles.form} onSubmit={redeem}>
        <label className={styles.field}>
          邀请码
          <div className={styles.input}>
            <Ticket size={18} aria-hidden="true" />
            <input
              type="text"
              autoComplete="one-time-code"
              value={invitationCode}
              onChange={(event) => setInvitationCode(event.target.value)}
              required
            />
          </div>
        </label>
        <label className={styles.field}>
          设置密码
          <div className={styles.input}>
            <KeyRound size={18} aria-hidden="true" />
            <input type="password" autoComplete="new-password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} required />
          </div>
        </label>
        {error && <p className={styles.error} role="alert">{error}</p>}
        <div className={styles.footer}>
          <Link className={styles.back} href="/login">返回登录</Link>
          <Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : UserPlus} disabled={submitting}>
            {submitting ? "正在创建账户" : "完成注册"}
          </Button>
        </div>
      </form>
    </AuthenticationShell>
  );
}
