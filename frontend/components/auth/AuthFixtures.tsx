"use client";

import { FormEvent, ReactNode, useState } from "react";
import {
  AtSign,
  CircleAlert,
  KeyRound,
  LoaderCircle,
  LogIn,
  ShieldCheck,
  Ticket,
  UserPlus,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import { AuthField } from "@/components/auth/AuthField";
import {
  PASSWORD_MIN_LENGTH,
  validateEmail,
  validateIdentifier,
  validateInvitationCode,
  validatePassword,
  validateUsername,
} from "@/components/auth/validation";
import { AuthStatusScreen } from "@/components/providers/AuthStatusScreen";
import { Button } from "@/components/ui/primitives";
import styles from "@/components/auth/AuthenticationShell.module.css";

type Touched<T extends string> = Partial<Record<T, boolean>>;

function FixtureCard({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section
      style={{
        border: "1px solid var(--borderColor-default)",
        borderRadius: "var(--oops-radius-xs)",
        padding: "var(--oops-space-4)",
        display: "grid",
        gap: "var(--oops-space-3)",
      }}
    >
      <div>
        <h3 style={{ margin: 0, fontSize: "var(--oops-text-md)" }}>{title}</h3>
        {note && (
          <p style={{ margin: "var(--oops-space-1) 0 0", fontSize: "var(--oops-text-xs)", color: "var(--fgColor-muted)" }}>
            {note}
          </p>
        )}
      </div>
      {children}
    </section>
  );
}

function EmbeddedShell({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <div
      style={{
        border: "1px dashed var(--borderColor-default)",
        borderRadius: "var(--oops-radius-sm)",
        padding: "var(--oops-space-4)",
        background: "var(--bgColor-muted)",
      }}
    >
      <AuthenticationShell title={title} description={description}>
        {children}
      </AuthenticationShell>
    </div>
  );
}

function SandboxLink({ label }: { label: string }) {
  return (
    <Link className={styles.back} href="/debug" onClick={(event) => event.preventDefault()}>
      {label}
    </Link>
  );
}

/* ---------------------------------- 登录 ---------------------------------- */

type LoginState = "idle" | "touched" | "submitting" | "failed";

function LoginFixture() {
  const [state, setState] = useState<LoginState>("idle");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState<Touched<"identifier" | "password">>({});

  const identifierError = validateIdentifier(identifier);
  const passwordError = validatePassword(password);
  const formValid = !identifierError && !passwordError;
  const showTouchedErrors = state !== "idle";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched({ identifier: true, password: true });
    if (!formValid) {
      setState("touched");
      return;
    }
    // 沙盒：停留 1.2 秒模拟网络往返，然后停在 failed 态供观察。
    setState("submitting");
    window.setTimeout(() => setState("failed"), 1200);
  }

  return (
    <FixtureCard
      title="登录表单"
      note={`状态：${state}。提交永远不发出请求。已知不足：表单未填完时按钮直接 disabled，没有提示原因。`}
    >
      <div style={{ display: "flex", gap: "var(--oops-space-2)", flexWrap: "wrap" }}>
        <Button size="small" variant={state === "idle" ? "primary" : "default"} onClick={() => { setState("idle"); setTouched({}); }}>初始态</Button>
        <Button size="small" variant={state === "touched" ? "primary" : "default"} onClick={() => { setTouched({ identifier: true, password: true }); setState("touched"); }}>校验错误态</Button>
        <Button size="small" variant={state === "failed" ? "primary" : "default"} onClick={() => { setTouched({ identifier: true, password: true }); setState("failed"); }}>提交失败态</Button>
        <Button size="small" onClick={() => { setState("idle"); setIdentifier(""); setPassword(""); setTouched({}); }}>清空</Button>
      </div>
      <EmbeddedShell title="登录 OopsNote" description="进入你的独立题库。">
        <form className={styles.form} onSubmit={submit} noValidate>
          <AuthField
            label="用户名或邮箱"
            icon={UserRound}
            name="identifier"
            autoComplete="username"
            value={identifier}
            onChange={setIdentifier}
            onBlur={() => setTouched((prev) => ({ ...prev, identifier: true }))}
            error={showTouchedErrors ? identifierError : null}
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
            error={showTouchedErrors ? passwordError : null}
            required
          />
          <div className={styles.footer}>
            <SandboxLink label="创建账号" />
            <Button type="submit" variant="primary" leadingVisual={state === "submitting" ? LoaderCircle : LogIn} disabled={state === "submitting" || !formValid}>
              {state === "submitting" ? "正在登录" : "登录"}
            </Button>
          </div>
          {state === "failed" && (
            <p role="alert" style={{ margin: 0, color: "var(--fgColor-danger)", fontSize: "var(--oops-text-xs)" }}>
              模拟失败：用户名、邮箱或密码不正确（真实页面此处只有 toast，刷新即丢）。
            </p>
          )}
        </form>
      </EmbeddedShell>
    </FixtureCard>
  );
}

/* ---------------------------------- 注册 ---------------------------------- */

type RegistrationMode = "open" | "invite" | "closed";
type RegisterField = "username" | "email" | "password" | "invitationCode";

function RegisterFixture() {
  const [mode, setMode] = useState<RegistrationMode>("invite");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invitationCode, setInvitationCode] = useState("");
  const [touched, setTouched] = useState<Touched<RegisterField>>({});
  const [submitting, setSubmitting] = useState(false);

  const invitationRequired = mode === "invite";
  const errors: Record<RegisterField, string | null> = {
    username: validateUsername(username),
    email: validateEmail(email),
    password: validatePassword(password),
    invitationCode: validateInvitationCode(invitationCode, invitationRequired),
  };
  const formValid = Object.values(errors).every((error) => !error);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched({ username: true, email: true, password: true, invitationCode: true });
    if (formValid) {
      setSubmitting(true);
      window.setTimeout(() => setSubmitting(false), 1200);
    }
  }

  return (
    <FixtureCard
      title="注册表单（三种注册模式）"
      note={`当前模式：${mode}。已知不足：注册成功后无邮箱验证环节；密码无强度指示。`}
    >
      <div style={{ display: "flex", gap: "var(--oops-space-2)", flexWrap: "wrap" }}>
        {(["open", "invite", "closed"] as const).map((item) => (
          <Button key={item} size="small" variant={mode === item ? "primary" : "default"} onClick={() => setMode(item)}>
            {item === "open" ? "开放注册" : item === "invite" ? "邀请制" : "关闭注册"}
          </Button>
        ))}
        <Button size="small" onClick={() => { setUsername(""); setEmail(""); setPassword(""); setInvitationCode(""); setTouched({}); }}>清空</Button>
      </div>
      {mode === "closed" ? (
        <EmbeddedShell title="创建账号" description="当前站点未开放注册，请联系管理员获取邀请。">
          <p style={{ margin: 0, fontSize: "var(--oops-text-sm)", color: "var(--fgColor-muted)" }}>
            （真实页面此模式下注册表单被禁用，仅保留返回登录入口。）
          </p>
        </EmbeddedShell>
      ) : (
        <EmbeddedShell title="创建账号" description="加入你的题库工作区。">
          <form className={styles.form} onSubmit={submit} noValidate>
            <AuthField label="用户名" icon={UserRound} name="username" autoComplete="username" value={username} onChange={setUsername} onBlur={() => setTouched((prev) => ({ ...prev, username: true }))} error={touched.username ? errors.username : null} required />
            <AuthField label="邮箱" icon={AtSign} type="email" name="email" autoComplete="email" value={email} onChange={setEmail} onBlur={() => setTouched((prev) => ({ ...prev, email: true }))} error={touched.email ? errors.email : null} required />
            <AuthField label="密码" icon={KeyRound} type="password" name="password" autoComplete="new-password" description={`至少 ${PASSWORD_MIN_LENGTH} 个字符。`} minLength={PASSWORD_MIN_LENGTH} maxLength={128} value={password} onChange={setPassword} onBlur={() => setTouched((prev) => ({ ...prev, password: true }))} error={touched.password ? errors.password : null} required />
            {invitationRequired && (
              <AuthField label="邀请码" icon={Ticket} name="invitationCode" value={invitationCode} onChange={setInvitationCode} onBlur={() => setTouched((prev) => ({ ...prev, invitationCode: true }))} error={touched.invitationCode ? errors.invitationCode : null} required />
            )}
            <div className={styles.footer}>
              <SandboxLink label="返回登录" />
              <Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : UserPlus} disabled={submitting}>
                {submitting ? "正在创建" : "创建账号"}
              </Button>
            </div>
          </form>
        </EmbeddedShell>
      )}
    </FixtureCard>
  );
}

/* ---------------------------------- Setup --------------------------------- */

function SetupFixture() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [confirmTouched, setConfirmTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const mismatch = confirmTouched && confirm.length > 0 && password !== confirm ? "两次输入的密码不一致" : null;

  return (
    <FixtureCard title="Setup 引导表单" note="已知不足：无密码强度指示；确认密码仅在输入后提示不一致。">
      <div style={{ display: "flex", gap: "var(--oops-space-2)", flexWrap: "wrap" }}>
        <Button size="small" onClick={() => { setName(""); setEmail(""); setPassword(""); setConfirm(""); setConfirmTouched(false); }}>清空</Button>
      </div>
      <EmbeddedShell title="初始化 OopsNote" description="创建第一个管理员账号。完成后即可登录，并在设置页配置 AI 渠道与成员邀请。">
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitting(true);
            window.setTimeout(() => setSubmitting(false), 1200);
          }}
          noValidate
        >
          <AuthField label="显示名称" icon={UserRound} name="name" autoComplete="name" value={name} onChange={setName} required />
          <AuthField label="邮箱" icon={AtSign} type="email" name="email" autoComplete="email" value={email} onChange={setEmail} required />
          <AuthField label="密码" icon={KeyRound} type="password" name="password" autoComplete="new-password" description="至少 12 个字符。" minLength={12} maxLength={128} value={password} onChange={setPassword} required />
          <AuthField label="确认密码" icon={KeyRound} type="password" name="confirm" autoComplete="new-password" minLength={12} maxLength={128} value={confirm} onChange={setConfirm} onBlur={() => setConfirmTouched(true)} error={mismatch} required />
          <div className={styles.footer}>
            <SandboxLink label="返回登录" />
            <Button type="submit" variant="primary" leadingVisual={submitting ? LoaderCircle : ShieldCheck} disabled={submitting}>
              {submitting ? "正在初始化" : "创建管理员"}
            </Button>
          </div>
        </form>
      </EmbeddedShell>
    </FixtureCard>
  );
}

/* ------------------------------- 会话状态屏 -------------------------------- */

function StatusScreensFixture() {
  const [variant, setVariant] = useState<"loading" | "error">("loading");
  return (
    <FixtureCard
      title="会话状态屏（AuthStatusScreen）"
      note="受保护页在会话检查中/失败时显示。已知不足：错误态唯一操作是刷新页面，后端持续不可用时形成死循环。"
    >
      <div style={{ display: "flex", gap: "var(--oops-space-2)", flexWrap: "wrap" }}>
        <Button size="small" variant={variant === "loading" ? "primary" : "default"} onClick={() => setVariant("loading")}>检查中</Button>
        <Button size="small" variant={variant === "error" ? "primary" : "default"} onClick={() => setVariant("error")}>会话错误</Button>
      </div>
      {variant === "error" ? (
        <div style={{ border: "1px dashed var(--borderColor-default)", borderRadius: "var(--oops-radius-sm)", overflow: "hidden" }}>
          <AuthStatusScreen error="模拟错误：无法确认登录状态（会同时弹一条 toast）" />
        </div>
      ) : (
        <div style={{ border: "1px dashed var(--borderColor-default)", borderRadius: "var(--oops-radius-sm)", overflow: "hidden" }}>
          <AuthStatusScreen />
        </div>
      )}
    </FixtureCard>
  );
}

/* -------------------------------- 字段变体 --------------------------------- */

function FieldVariantsFixture() {
  const [showDescription, setShowDescription] = useState(true);
  const [withError, setWithError] = useState(false);
  return (
    <FixtureCard title="AuthField 字段变体" note="逐项核对间距、图标对齐、错误色与触屏目标高度。">
      <div style={{ display: "flex", gap: "var(--oops-space-2)", flexWrap: "wrap" }}>
        <Button size="small" variant={showDescription ? "primary" : "default"} onClick={() => setShowDescription((prev) => !prev)}>描述文本</Button>
        <Button size="small" variant={withError ? "primary" : "default"} onClick={() => setWithError((prev) => !prev)}>错误态</Button>
      </div>
      <EmbeddedShell title="字段变体" description="对照真实表单的单字段状态。">
        <div style={{ display: "grid", gap: "var(--oops-space-4)" }}>
          <AuthField label="基础输入" icon={UserRound} name="demo-basic" value="" onChange={() => undefined} description={showDescription ? "这是一段描述文本。" : undefined} error={withError ? "这是错误提示。" : null} />
          <AuthField label="带占位符" icon={AtSign} type="email" name="demo-placeholder" placeholder="you@example.com" value="" onChange={() => undefined} error={withError ? "请输入有效的邮箱地址。" : null} />
          <AuthField label="超长标签溢出测试——这里有一段非常非常长的标签文字用来检查换行" icon={KeyRound} type="password" name="demo-long" value="" onChange={() => undefined} error={withError ? "密码至少需要 12 个字符。" : null} />
        </div>
      </EmbeddedShell>
    </FixtureCard>
  );
}

export function AuthFixtures() {
  return (
    <div id="auth-fixtures" style={{ display: "grid", gap: "var(--oops-space-4)" }}>
      <FixtureCard title="账号 / 认证 UI 测试台" note="所有提交只在组件内模拟，不发网络请求、不改任何数据。">
        <p style={{ margin: 0, fontSize: "var(--oops-text-xs)", color: "var(--fgColor-muted)" }}>
          覆盖：登录、注册（开放/邀请/关闭）、Setup 引导、会话状态屏、字段变体。
          每个卡片标注了当前已知的体验不足，测试时可直接对照确认。
        </p>
      </FixtureCard>
      <LoginFixture />
      <RegisterFixture />
      <SetupFixture />
      <StatusScreensFixture />
      <FieldVariantsFixture />
    </div>
  );
}
