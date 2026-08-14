"use client";

import { FormEvent, useState } from "react";
import { AtSign, KeyRound, LoaderCircle, ShieldCheck, UserRound } from "lucide-react";
import Link from "next/link";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import styles from "@/components/auth/AuthenticationShell.module.css";
import { Button } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

export function SetupForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    if (password !== confirm) {
      setError("两次输入的密码不一致");
      setSubmitting(false);
      return;
    }
    try {
      const response = await fetch("/api/admin/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), name: name.trim(), password }),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) {
        setError(payload.error || "初始化失败");
        return;
      }
      window.location.replace(`/login?identifier=${encodeURIComponent(email.trim())}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "初始化请求失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthenticationShell
      title="初始化 OopsNote"
      description="创建第一个管理员账号。完成后即可登录，并在设置页配置 AI 渠道与成员邀请。"
    >
      <ErrorBanner message={error ?? ""} title="初始化失败" />
      <form className={styles.form} onSubmit={submit}>
        <label className={styles.field}>显示名称<div className={styles.input}><UserRound size={18} aria-hidden="true" /><input type="text" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} required /></div></label>
        <label className={styles.field}>邮箱<div className={styles.input}><AtSign size={18} aria-hidden="true" /><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></div></label>
        <label className={styles.field}>密码<div className={styles.input}><KeyRound size={18} aria-hidden="true" /><input type="password" autoComplete="new-password" minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} required /></div><span className={styles.hint}>至少 12 个字符。</span></label>
        <label className={styles.field}>确认密码<div className={styles.input}><KeyRound size={18} aria-hidden="true" /><input type="password" autoComplete="new-password" minLength={12} maxLength={128} value={confirm} onChange={(event) => setConfirm(event.target.value)} required /></div></label>
        <div className={styles.footer}><Link className={styles.back} href="/login">返回登录</Link><Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : ShieldCheck} disabled={submitting}>{submitting ? "正在初始化" : "创建管理员"}</Button></div>
      </form>
    </AuthenticationShell>
  );
}
