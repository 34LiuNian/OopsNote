"use client";

import { FormEvent, useEffect, useState } from "react";
import { AtSign, KeyRound, LoaderCircle, Mail, Ticket, UserPlus } from "lucide-react";
import Link from "next/link";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import styles from "@/components/auth/AuthenticationShell.module.css";
import { Button } from "@/components/ui/primitives";
import { authClient } from "@/lib/better-auth-client";

type RegistrationMode = "closed" | "invite" | "open";

function initialCode(): string {
  if (typeof window === "undefined") return "";
  const params = new URL(window.location.href).searchParams;
  return params.get("code") || params.get("token") || "";
}

export default function RegisterPage() {
  const [mode, setMode] = useState<RegistrationMode | null>(null);
  const [policyLoaded, setPolicyLoaded] = useState(false);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invitationCode, setInvitationCode] = useState(initialCode);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void authClient.$fetch<{ mode: RegistrationMode }>("/registration-policy").then((result) => {
      if (result.data) setMode(result.data.mode);
      else setError(result.error?.message || "无法读取注册策略");
    }).finally(() => setPolicyLoaded(true));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const result = await authClient.$fetch("/register", {
      method: "POST",
      body: {
        username: username.trim(),
        email: email.trim(),
        password,
        invitationCode: invitationCode.trim() || undefined,
      },
    });
    if (result.error) {
      setError(result.error.message || "注册失败");
      setSubmitting(false);
      return;
    }
    window.location.replace(`/login?identifier=${encodeURIComponent(username.trim())}`);
  }

  const closed = mode === "closed";
  const invitationRequired = mode === "invite";
  return (
    <AuthenticationShell
      title="注册 OopsNote"
      description={closed ? "当前未开放新账号注册。" : invitationRequired ? "使用邀请码创建你的独立账号。" : "创建你的独立账号。"}
    >
      {!policyLoaded ? (
        <div className={styles.status}><LoaderCircle className={styles.spinner} aria-hidden="true" /><p>正在读取注册策略...</p></div>
      ) : mode === null ? (
        <div className={styles.status}><p className={styles.error} role="alert">{error || "无法读取注册策略"}</p><Link className={styles.back} href="/login">返回登录</Link></div>
      ) : closed ? (
        <div className={styles.footer}><Link className={styles.back} href="/login">返回登录</Link></div>
      ) : (
        <form className={styles.form} onSubmit={submit}>
          <label className={styles.field}>用户名<div className={styles.input}><AtSign size={18} aria-hidden="true" /><input type="text" autoComplete="username" minLength={3} maxLength={32} pattern="[A-Za-z0-9_.]+" value={username} onChange={(event) => setUsername(event.target.value)} required /></div><span className={styles.hint}>3–32 位，可使用字母、数字、下划线和点。</span></label>
          <label className={styles.field}>邮箱<div className={styles.input}><Mail size={18} aria-hidden="true" /><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></div></label>
          <label className={styles.field}>密码<div className={styles.input}><KeyRound size={18} aria-hidden="true" /><input type="password" autoComplete="new-password" minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} required /></div><span className={styles.hint}>至少 12 个字符。</span></label>
          <label className={styles.field}>邀请码{!invitationRequired && <span className={styles.optional}>可选</span>}<div className={styles.input}><Ticket size={18} aria-hidden="true" /><input type="text" autoComplete="one-time-code" value={invitationCode} onChange={(event) => setInvitationCode(event.target.value)} required={invitationRequired} /></div></label>
          {error && <p className={styles.error} role="alert">{error}</p>}
          <div className={styles.footer}><Link className={styles.back} href="/login">返回登录</Link><Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : UserPlus} disabled={submitting}>{submitting ? "正在创建账号" : "注册"}</Button></div>
        </form>
      )}
    </AuthenticationShell>
  );
}
