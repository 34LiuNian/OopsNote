"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { RefreshCw, Save, ShieldAlert, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Button, Select, TextInput } from "@/components/ui/primitives";
import { isAdminUser } from "@/lib/auth";
import { notify } from "@/lib/notify";
import styles from "./access.module.css";

type RegistrationMode = "closed" | "invite" | "open";
type Policy = { mode: RegistrationMode; openDailySuccessLimit: number };

export default function RegistrationAccessPage() {
  const { user, loading: authLoading } = useAuth();
  const [mode, setMode] = useState<RegistrationMode>("invite");
  const [openDailySuccessLimit, setOpenDailySuccessLimit] = useState(5);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const response = await fetch("/api/admin/registration-policy", { cache: "no-store" });
      const payload = await response.json() as Policy & { error?: string };
      if (!response.ok) throw new Error(payload.error || "无法读取注册策略");
      setMode(payload.mode);
      setOpenDailySuccessLimit(payload.openDailySuccessLimit);
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "无法读取注册策略");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading || !isAdminUser(user)) return;
    void load();
  }, [authLoading, load, user]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    try {
      const response = await fetch("/api/admin/registration-policy", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mode, openDailySuccessLimit }),
      });
      const payload = await response.json() as Policy & { error?: string };
      if (!response.ok) throw new Error(payload.error || "保存失败");
      setMode(payload.mode);
      setOpenDailySuccessLimit(payload.openDailySuccessLimit);
      notify.success({ title: "注册策略已保存" });
    } catch (reason) {
      notify.error({ title: "保存失败", description: reason instanceof Error ? reason.message : "注册策略更新失败" });
    } finally {
      setSaving(false);
    }
  }

  if (!authLoading && !isAdminUser(user)) return <p><ShieldAlert size={18} /> 注册与访问仅管理员可用。</p>;

  return (
    <div className={styles.page}>
      <PageHeader title="注册与访问" description="控制新用户如何进入 OopsNote" />
      <ErrorBanner message={loadError} title="注册策略加载失败" />
      {loadError ? <Button variant="secondary" size="small" leadingVisual={RefreshCw} onClick={() => void load()}>重新加载</Button> : null}
      <form className={styles.panel} onSubmit={save}>
        <div className={styles.heading}><ShieldCheck size={22} aria-hidden="true" /><div><h2>用户注册</h2><p>所有注册方式都要求唯一用户名、邮箱和密码。</p></div></div>
        <label className={styles.field}>
          注册模式
          <Select value={mode} onValueChange={(value) => setMode(value as RegistrationMode)} disabled={loading || Boolean(loadError)} aria-label="注册模式">
            <Select.Option value="closed">关闭注册</Select.Option>
            <Select.Option value="invite">仅邀请码注册</Select.Option>
            <Select.Option value="open">开放注册</Select.Option>
          </Select>
          <span>{mode === "closed" ? "只有管理员可以创建新用户。" : mode === "invite" ? "用户必须持有未过期且仍有次数的邀请码。" : "任何人都可以创建用户账号。"}</span>
        </label>
        <label className={styles.field}>
          开放注册默认每日额度
          <TextInput type="number" min="0" max="1000000" value={openDailySuccessLimit} onChange={(event) => setOpenDailySuccessLimit(Number(event.target.value))} disabled={loading || Boolean(loadError) || mode !== "open"} required aria-label="开放注册默认每日额度" />
          <span>邀请码注册使用邀请码单独设置的额度。</span>
        </label>
        <div className={styles.emailPolicy}><strong>邮箱要求</strong><span>所有用户必须填写唯一邮箱；当前不发送验证邮件，保留后续验证升级空间。</span></div>
        <div className={styles.footer}><Button type="submit" variant="primary" leadingVisual={Save} disabled={loading || Boolean(loadError) || saving}>{saving ? "正在保存" : "保存"}</Button></div>
      </form>
    </div>
  );
}
