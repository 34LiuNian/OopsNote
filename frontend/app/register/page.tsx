"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { AtSign, KeyRound, LoaderCircle, Mail, Ticket, UserPlus } from "lucide-react";
import Link from "next/link";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import { AuthField } from "@/components/auth/AuthField";
import { validateEmail, validateInvitationCode, validatePassword, validateUsername } from "@/components/auth/validation";
import styles from "@/components/auth/AuthenticationShell.module.css";
import { Button } from "@/components/ui/primitives";
import { authClient } from "@/lib/better-auth-client";
import { notify } from "@/lib/notify";

type RegistrationMode = "closed" | "invite" | "open";
type FieldName = "username" | "email" | "password" | "invitationCode";

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
  const [touched, setTouched] = useState({ username: false, email: false, password: false, invitationCode: false });
  const [submitting, setSubmitting] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    void authClient.$fetch<{ mode: RegistrationMode }>("/registration-policy").then((result) => {
      if (result.data) setMode(result.data.mode);
      else notify.error({ title: "无法读取注册策略", description: result.error?.message });
    }).catch((reason) => {
      notify.error({ title: "无法读取注册策略", description: reason instanceof Error ? reason.message : undefined });
    }).finally(() => setPolicyLoaded(true));
  }, []);

  const closed = mode === "closed";
  const invitationRequired = mode === "invite";

  const errors = {
    username: validateUsername(username),
    email: validateEmail(email),
    password: validatePassword(password),
    invitationCode: validateInvitationCode(invitationCode, invitationRequired),
  };
  const formValid = !errors.username && !errors.email && !errors.password && !errors.invitationCode;

  function focusInvalid(field: FieldName) {
    const control = formRef.current?.elements.namedItem(field);
    if (control instanceof HTMLElement) control.focus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched({ username: true, email: true, password: true, invitationCode: true });
    const order: FieldName[] = ["username", "email", "password", "invitationCode"];
    const firstInvalid = order.find((field) => errors[field]);
    if (firstInvalid) return focusInvalid(firstInvalid);
    setSubmitting(true);
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
        notify.error({ title: "注册失败", description: result.error.message || "请稍后再试" });
        return;
      }
      window.location.replace(`/login?identifier=${encodeURIComponent(username.trim())}`);
    } catch (reason) {
      notify.error({ title: "注册失败", description: reason instanceof Error ? reason.message : "注册请求失败" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthenticationShell
      title="注册 OopsNote"
      description={closed ? "当前未开放新账号注册。" : invitationRequired ? "使用邀请码创建你的独立账号。" : "创建你的独立账号。"}
    >
      {!policyLoaded ? (
        <div className={styles.skeleton} aria-hidden="true">
          <div className={styles.skeletonRow} />
          <div className={styles.skeletonRow} />
          <div className={styles.skeletonRow} />
          <div className={styles.skeletonFooter} />
        </div>
      ) : mode === null ? (
        <div className={styles.status}><p>注册策略当前不可用。</p><Link className={styles.back} href="/login">返回登录</Link></div>
      ) : closed ? (
        <div className={styles.footer}><Link className={styles.back} href="/login">返回登录</Link></div>
      ) : (
        <form ref={formRef} className={styles.form} onSubmit={submit} noValidate>
          <AuthField
            label="用户名"
            icon={AtSign}
            name="username"
            autoComplete="username"
            description="3–32 位，可使用字母、数字、下划线和点。"
            value={username}
            onChange={setUsername}
            onBlur={() => setTouched((prev) => ({ ...prev, username: true }))}
            error={touched.username ? errors.username : null}
            minLength={3}
            maxLength={32}
            pattern="[A-Za-z0-9_.]+"
            required
          />
          <AuthField
            label="邮箱"
            icon={Mail}
            type="email"
            name="email"
            autoComplete="email"
            value={email}
            onChange={setEmail}
            onBlur={() => setTouched((prev) => ({ ...prev, email: true }))}
            error={touched.email ? errors.email : null}
            required
          />
          <AuthField
            label="密码"
            icon={KeyRound}
            type="password"
            name="password"
            autoComplete="new-password"
            description="至少 12 个字符。"
            value={password}
            onChange={setPassword}
            onBlur={() => setTouched((prev) => ({ ...prev, password: true }))}
            error={touched.password ? errors.password : null}
            minLength={12}
            maxLength={128}
            required
          />
          <AuthField
            label="邀请码"
            labelSuffix={!invitationRequired ? <span className={styles.optional}>可选</span> : undefined}
            icon={Ticket}
            name="invitationCode"
            autoComplete="one-time-code"
            value={invitationCode}
            onChange={setInvitationCode}
            onBlur={() => setTouched((prev) => ({ ...prev, invitationCode: true }))}
            error={touched.invitationCode ? errors.invitationCode : null}
            required={invitationRequired}
          />
          <div className={styles.footer}>
            <Link className={styles.back} href="/login">返回登录</Link>
            <Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : UserPlus} disabled={submitting || !formValid}>
              {submitting ? "正在创建账号" : "注册"}
            </Button>
          </div>
        </form>
      )}
    </AuthenticationShell>
  );
}
