"use client";

import { FormEvent, useEffect, useState } from "react";
import { AtSign, KeyRound, LoaderCircle, Mail, Ticket, UserPlus } from "lucide-react";
import Link from "next/link";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import styles from "@/components/auth/AuthenticationShell.module.css";
import { Button, PasswordInput, TextInput } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
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
    }).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "无法读取注册策略");
    }).finally(() => setPolicyLoaded(true));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
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
        return;
      }
      window.location.replace(`/login?identifier=${encodeURIComponent(username.trim())}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "注册请求失败");
    } finally {
      setSubmitting(false);
    }
  }

  const closed = mode === "closed";
  const invitationRequired = mode === "invite";
  return (
    <AuthenticationShell
      title="注册 OopsNote"
      description={closed ? "当前未开放新账号注册。" : invitationRequired ? "使用邀请码创建你的独立账号。" : "创建你的独立账号。"}
    >
      <ErrorBanner message={error ?? ""} title="注册失败" />
      {!policyLoaded ? (
        <div className={styles.status}><LoaderCircle className={styles.spinner} aria-hidden="true" /><p>正在读取注册策略...</p></div>
      ) : mode === null ? (
        <div className={styles.status}><p>注册策略当前不可用。</p><Link className={styles.back} href="/login">返回登录</Link></div>
      ) : closed ? (
        <div className={styles.footer}><Link className={styles.back} href="/login">返回登录</Link></div>
      ) : (
        <form className={styles.form} onSubmit={submit}>
          <TextInput className={styles.input} label="用户名" leadingVisual={AtSign} type="text" autoComplete="username" minLength={3} maxLength={32} pattern="[A-Za-z0-9_.]+" value={username} onChange={(event) => setUsername(event.target.value)} required description="3–32 位，可使用字母、数字、下划线和点。" />
          <TextInput className={styles.input} label="邮箱" leadingVisual={Mail} type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <PasswordInput className={styles.input} label="密码" leftSection={<KeyRound size={18} aria-hidden="true" />} autoComplete="new-password" minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} required description="至少 12 个字符。" />
          <TextInput className={styles.input} label={<>邀请码{!invitationRequired && <span className={styles.optional}>可选</span>}</>} leadingVisual={Ticket} type="text" autoComplete="one-time-code" value={invitationCode} onChange={(event) => setInvitationCode(event.target.value)} required={invitationRequired} />
          <div className={styles.footer}><Link className={styles.back} href="/login">返回登录</Link><Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : UserPlus} disabled={submitting}>{submitting ? "正在创建账号" : "注册"}</Button></div>
        </form>
      )}
    </AuthenticationShell>
  );
}
