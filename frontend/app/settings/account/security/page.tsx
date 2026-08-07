"use client";

import { FormEvent, useState } from "react";
import { KeyRound, Save, ShieldCheck } from "lucide-react";
import { AccountSettingsNav } from "@/components/account/AccountSettingsNav";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button, TextInput } from "@/components/ui/primitives";
import { authClient } from "@/lib/better-auth-client";
import { notify } from "@/lib/notify";
import styles from "../account.module.css";

export default function AccountSecurityPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (newPassword !== confirmation) {
      notify.error({ title: "两次输入的新密码不一致" });
      return;
    }
    setSaving(true);
    const result = await authClient.changePassword({ currentPassword, newPassword, revokeOtherSessions: true });
    setSaving(false);
    if (result.error) {
      notify.error({ title: "密码修改失败", description: result.error.message });
      return;
    }
    setCurrentPassword("");
    setNewPassword("");
    setConfirmation("");
    notify.success({ title: "密码已更新", description: "其他设备上的登录会话已撤销。" });
  }

  return (
    <div className={styles.page}>
      <PageHeader title="个人账号" description="管理个人资料、账号安全和额度" />
      <AccountSettingsNav />
      <form className={styles.panel} onSubmit={submit}>
        <div className={styles.panelHeading}><ShieldCheck size={22} aria-hidden="true" /><div><h2>账号安全</h2><p>修改密码后会撤销其他设备上的登录会话。</p></div></div>
        <div className={styles.fields}>
          <TextInput className={styles.fullField} label="当前密码" type="password" autoComplete="current-password" leadingVisual={KeyRound} value={currentPassword} onChange={(event) => setCurrentPassword(event.currentTarget.value)} required block />
          <TextInput label="新密码" type="password" autoComplete="new-password" minLength={12} maxLength={128} leadingVisual={KeyRound} value={newPassword} onChange={(event) => setNewPassword(event.currentTarget.value)} required block />
          <TextInput label="确认新密码" type="password" autoComplete="new-password" minLength={12} maxLength={128} leadingVisual={KeyRound} value={confirmation} onChange={(event) => setConfirmation(event.currentTarget.value)} required block />
        </div>
        <div className={styles.footer}><span /><Button type="submit" variant="primary" leadingVisual={Save} disabled={saving}>{saving ? "正在更新" : "更新密码"}</Button></div>
      </form>
    </div>
  );
}
