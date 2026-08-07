"use client";

import { FormEvent, useMemo, useState } from "react";
import { Camera, Mail, Save, UserRound } from "lucide-react";
import { Button, TextInput } from "@/components/ui/primitives";
import { PageHeader } from "@/components/layout/PageHeader";
import { authClient } from "@/lib/better-auth-client";
import { InitialAvatar } from "@/components/ui/InitialAvatar";
import styles from "./account.module.css";

export default function AccountPage() {
  const session = authClient.useSession();
  const user = session.data?.user;
  const [draftName, setDraftName] = useState<string | null>(null);
  const [draftImage, setDraftImage] = useState<string | null>(null);
  const [draftEmail, setDraftEmail] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  const name = draftName ?? user?.name ?? "";
  const image = draftImage ?? user?.image ?? "";
  const email = draftEmail ?? user?.email ?? "";
  const currentEmail = user?.email ?? "";

  const avatarLabel = useMemo(() => name || user?.email || "OopsNote", [name, user?.email]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    const profileResult = await authClient.updateUser({ name: name.trim(), image: image.trim() || null });
    if (profileResult.error) {
      setSaving(false);
      setMessage(profileResult.error.message || "保存失败");
      return;
    }
    if (email.trim().toLowerCase() !== currentEmail.toLowerCase()) {
      const emailResult = await authClient.changeEmail({ newEmail: email.trim(), callbackURL: "/settings/account" });
      if (emailResult.error) {
        setSaving(false);
        setMessage(`资料已保存，但邮箱未更新：${emailResult.error.message || "请重新登录后再试"}`);
        return;
      }
    }
    setSaving(false);
    setDraftName(null);
    setDraftImage(null);
    setDraftEmail(null);
    setMessage("账户信息已保存");
  }

  if (session.isPending) return <p className={styles.state}>正在加载账户信息...</p>;
  if (!user) return <p className={styles.state}>请先登录。</p>;

  return (
    <div className={styles.page}>
      <PageHeader title="我的账户" description="管理你的显示信息和登录资料" />
      <form className={styles.panel} onSubmit={save}>
        <div className={styles.panelHeading}>
          <UserRound size={22} aria-hidden="true" />
          <div><h2>账户详情</h2><p>这些资料只用于 OopsNote 内部账户展示。</p></div>
        </div>
        <div className={styles.avatarRow}>
          <InitialAvatar name={avatarLabel} image={image} size={88} />
          <div><strong>头像</strong><p>填写图片链接后可预览头像。</p><span className={styles.hint}><Camera size={14} aria-hidden="true" /> 支持 HTTPS 图片地址</span></div>
        </div>
        <div className={styles.fields}>
          <TextInput label="显示名称" value={name} onChange={(event) => setDraftName(event.currentTarget.value)} required block />
          <TextInput label="电子邮件" value={email} onChange={(event) => setDraftEmail(event.currentTarget.value)} type="email" leadingVisual={Mail} required block />
          <TextInput className={styles.fullField} label="头像链接" value={image} onChange={(event) => setDraftImage(event.currentTarget.value)} placeholder="https://..." block />
        </div>
        <div className={styles.footer}><p role="status">{message}</p><Button type="submit" variant="primary" leadingVisual={Save} disabled={saving}>{saving ? "保存中..." : "保存"}</Button></div>
      </form>
    </div>
  );
}
