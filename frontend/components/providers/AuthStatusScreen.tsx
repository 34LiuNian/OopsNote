"use client";

import { CircleAlert, LoaderCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { AuthenticationShell } from "@/components/auth/AuthenticationShell";
import styles from "@/components/auth/AuthenticationShell.module.css";
import { useEffect } from "react";
import { notify } from "@/lib/notify";

type AuthStatusScreenProps = { error?: string | null };

export function AuthStatusScreen({ error }: AuthStatusScreenProps) {
  useEffect(() => {
    if (error) notify.error({ title: "登录失败", description: error });
  }, [error]);
  const isError = Boolean(error);
  const title = isError ? "登录未完成" : "正在前往登录";
  const detail = isError ? error : "正在打开登录页面";

  return (
    <AuthenticationShell title={title} description={detail || ""}>
      <section className={styles.status} aria-live="polite" aria-busy={!isError}>
        <div className={styles.statusIcon} data-error={isError}>
          {isError ? <CircleAlert size={22} aria-hidden="true" /> : <LoaderCircle size={22} aria-hidden="true" />}
        </div>
        {!isError && <div className={styles.statusProgress} aria-hidden="true"><span /></div>}
        {isError && <Button type="button" variant="secondary" leadingVisual={RotateCcw} onClick={() => window.location.reload()}>重新登录</Button>}
      </section>
    </AuthenticationShell>
  );
}
