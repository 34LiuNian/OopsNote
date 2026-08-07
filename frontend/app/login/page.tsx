"use client";

import { FormEvent, useState } from "react";
import { KeyRound, LoaderCircle, LogIn, Mail } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import styles from "@/components/auth/AuthenticationShell.module.css";
import { authClient } from "@/lib/better-auth-client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const returnTo = new URL(window.location.href).searchParams.get("returnTo") || "/library";
    const result = await authClient.signIn.email({ email, password });
    if (result.error) {
      setError(result.error.message || "邮箱或密码不正确");
      setSubmitting(false);
      return;
    }
    window.location.replace(returnTo.startsWith("/") ? returnTo : "/library");
  }

  return (
    <AuthenticationShell title="登录 OopsNote" description="使用管理员提供的内测账户进入你的独立题库。">
      <form className={styles.form} onSubmit={submit}>
        <label className={styles.field}>邮箱<div className={styles.input}><Mail size={18} aria-hidden="true" /><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></div></label>
        <label className={styles.field}>密码<div className={styles.input}><KeyRound size={18} aria-hidden="true" /><input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} required /></div></label>
        {error && <p className={styles.error} role="alert">{error}</p>}
        <div className={styles.footer}><span /><Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : LogIn} disabled={submitting}>{submitting ? "正在登录" : "登录"}</Button></div>
      </form>
    </AuthenticationShell>
  );
}
