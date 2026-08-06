"use client";

import { FormEvent, useState } from "react";
import { KeyRound, LoaderCircle, LogIn, Mail } from "lucide-react";
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
    const returnTo = new URL(window.location.href).searchParams.get("returnTo") || "/";
    const result = await authClient.signIn.email({ email, password });
    if (result.error) {
      setError(result.error.message || "邮箱或密码不正确");
      setSubmitting(false);
      return;
    }
    window.location.replace(returnTo.startsWith("/") ? returnTo : "/");
  }

  return (
    <main className="oops-login-page">
      <section className="oops-login-panel" aria-labelledby="login-title">
        <div className="oops-login-heading">
          <div className="oops-login-heading__brand"><span aria-hidden="true" />OopsNote</div>
          <h1 id="login-title">登录</h1>
          <p>使用管理员提供的内测账号进入你的独立题库。</p>
        </div>
        <form onSubmit={submit}>
          <label>
            <span>邮箱</span>
            <div className="oops-login-input"><Mail size={17} aria-hidden="true" /><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></div>
          </label>
          <label>
            <span>密码</span>
            <div className="oops-login-input"><KeyRound size={17} aria-hidden="true" /><input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} required /></div>
          </label>
          {error && <p className="oops-login-error" role="alert">{error}</p>}
          <button type="submit" disabled={submitting}>
            {submitting ? <LoaderCircle size={17} className="oops-login-spinner" aria-hidden="true" /> : <LogIn size={17} aria-hidden="true" />}
            {submitting ? "正在登录" : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
