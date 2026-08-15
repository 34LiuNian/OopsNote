"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { KeyRound, LoaderCircle, LogIn, UserRound } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/primitives";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import { AuthField } from "@/components/auth/AuthField";
import { validateIdentifier, validatePassword } from "@/components/auth/validation";
import styles from "@/components/auth/AuthenticationShell.module.css";
import { authClient } from "@/lib/better-auth-client";
import { notify } from "@/lib/notify";

export default function LoginPage() {
  const [identifier, setIdentifier] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URL(window.location.href).searchParams.get("identifier") || "";
  });
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState({ identifier: false, password: false });
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    void authClient.$fetch<{ mode: "closed" | "invite" | "open" }>("/registration-policy").then((result) => {
      if (result.data) setRegistrationOpen(result.data.mode !== "closed");
    }).catch((reason) => {
      notify.error({ title: "无法读取注册策略", description: reason instanceof Error ? reason.message : undefined });
    });
  }, []);

  const identifierError = validateIdentifier(identifier);
  const passwordError = validatePassword(password);
  const formValid = !identifierError && !passwordError;

  function focusFirstInvalid(field: "identifier" | "password") {
    const control = formRef.current?.elements.namedItem(field);
    if (control instanceof HTMLElement) control.focus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched({ identifier: true, password: true });
    if (identifierError) return focusFirstInvalid("identifier");
    if (passwordError) return focusFirstInvalid("password");
    setSubmitting(true);
    try {
      const returnTo = new URL(window.location.href).searchParams.get("returnTo") || "/library";
      const value = identifier.trim();
      const result = value.includes("@")
        ? await authClient.signIn.email({ email: value, password })
        : await authClient.signIn.username({ username: value, password });
      if (result.error) {
        notify.error({ title: "登录失败", description: result.error.message || "用户名、邮箱或密码不正确" });
        return;
      }
      window.location.replace(returnTo.startsWith("/") ? returnTo : "/library");
    } catch (reason) {
      notify.error({ title: "登录失败", description: reason instanceof Error ? reason.message : "登录请求失败" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthenticationShell title="登录 OopsNote" description="进入你的独立题库。">
      <form ref={formRef} className={styles.form} onSubmit={submit} noValidate>
        <AuthField
          label="用户名或邮箱"
          icon={UserRound}
          name="identifier"
          autoComplete="username"
          value={identifier}
          onChange={setIdentifier}
          onBlur={() => setTouched((prev) => ({ ...prev, identifier: true }))}
          error={touched.identifier ? identifierError : null}
          required
        />
        <AuthField
          label="密码"
          icon={KeyRound}
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
          onBlur={() => setTouched((prev) => ({ ...prev, password: true }))}
          error={touched.password ? passwordError : null}
          required
        />
        <div className={styles.footer}>
          {registrationOpen ? <Link className={styles.back} href="/register">创建账号</Link> : <span />}
          <Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : LogIn} disabled={submitting || !formValid}>
            {submitting ? "正在登录" : "登录"}
          </Button>
        </div>
      </form>
    </AuthenticationShell>
  );
}
