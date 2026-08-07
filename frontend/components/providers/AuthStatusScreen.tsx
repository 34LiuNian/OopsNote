"use client";

import { CircleAlert, LoaderCircle, RotateCcw } from "lucide-react";

type AuthStatusScreenProps = {
  phase: "signin" | "callback";
  error?: string | null;
};

export function AuthStatusScreen({ phase, error }: AuthStatusScreenProps) {
  const isError = Boolean(error);
  const title = isError
    ? "登录未完成"
    : phase === "signin"
      ? "正在前往登录"
      : "正在完成登录";
  const detail = isError
    ? error
    : phase === "signin"
      ? "正在打开登录页面"
      : "正在验证身份信息";

  return (
    <main className="oops-auth-status" aria-busy={!isError}>
      <div className="oops-auth-status__brand" aria-label="OopsNote">
        <span className="oops-auth-status__mark" aria-hidden="true" />
        <span>OopsNote</span>
      </div>
      <section className="oops-auth-status__content" aria-live="polite">
        <div className={`oops-auth-status__indicator${isError ? " is-error" : ""}`}>
          {isError ? <CircleAlert size={24} aria-hidden="true" /> : <LoaderCircle size={24} aria-hidden="true" />}
        </div>
        <h1>{title}</h1>
        <p>{detail}</p>
        {isError && (
          <button type="button" onClick={() => window.location.reload()}>
            <RotateCcw size={16} aria-hidden="true" />
            重新登录
          </button>
        )}
      </section>
    </main>
  );
}
