"use client";

import { FormEvent, useState } from "react";
import { KeyRound, LoaderCircle, UserPlus } from "lucide-react";
import { authClient } from "@/lib/better-auth-client";

export default function InvitePage() {
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function redeem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = new URL(window.location.href).searchParams.get("token") || "";
    if (!token) { setError("邀请链接缺少 token"); return; }
    setSubmitting(true);
    setError(null);
    const result = await authClient.$fetch("/invite/redeem", { method: "POST", body: { token, password } });
    if (result.error) {
      setError(result.error.message || "邀请兑换失败");
      setSubmitting(false);
      return;
    }
    window.location.replace("/login");
  }

  return (
    <main className="oops-login-page">
      <section className="oops-login-panel" aria-labelledby="invite-title">
        <div className="oops-login-heading"><div className="oops-login-heading__brand"><span aria-hidden="true" />OopsNote</div><h1 id="invite-title">设置内测密码</h1><p>完成后使用你的邮箱和新密码登录。</p></div>
        <form onSubmit={redeem}>
          <label><span>密码</span><div className="oops-login-input"><KeyRound size={17} aria-hidden="true" /><input type="password" autoComplete="new-password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} required /></div></label>
          {error && <p className="oops-login-error" role="alert">{error}</p>}
          <button type="submit" disabled={submitting}>{submitting ? <LoaderCircle size={17} className="oops-login-spinner" /> : <UserPlus size={17} />}{submitting ? "正在创建账号" : "完成注册"}</button>
        </form>
      </section>
    </main>
  );
}
