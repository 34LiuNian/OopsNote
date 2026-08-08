"use client";

import { FormEvent, useMemo, useState } from "react";
import { AtSign, Camera, Mail, Save, UserRound } from "lucide-react";
import { AccountSettingsNav } from "@/components/account/AccountSettingsNav";
import { PageHeader } from "@/components/layout/PageHeader";
import { InitialAvatar } from "@/components/ui/InitialAvatar";
import { Button, TextInput } from "@/components/ui/primitives";
import { authClient } from "@/lib/better-auth-client";
import { notify } from "@/lib/notify";
import styles from "./account.module.css";

export default function AccountPage() {
  const session = authClient.useSession();
  const user = session.data?.user;
  const identity = user as (typeof user & { username?: string | null; displayUsername?: string | null }) | undefined;
  const [draftImage, setDraftImage] = useState<string | null>(null);
  const [draftEmail, setDraftEmail] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const username = identity?.displayUsername || identity?.username || identity?.name || "";
  const image = draftImage ?? user?.image ?? "";
  const email = draftEmail ?? user?.email ?? "";
  const currentEmail = user?.email ?? "";
  const avatarLabel = useMemo(() => username || email || "OopsNote", [email, username]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const profileResult = await authClient.updateUser({ image: image.trim() || null });
    if (profileResult.error) {
      notify.error({ title: "保存失败", description: profileResult.error.message });
      setSaving(false);
      return;
    }
    if (email.trim().toLowerCase() !== currentEmail.toLowerCase()) {
      const emailResult = await authClient.changeEmail({ newEmail: email.trim(), callbackURL: "/settings/account" });
      if (emailResult.error) {
        notify.error({ title: "头像已保存，邮箱更新失败", description: emailResult.error.message });
        setSaving(false);
        return;
      }
    }
    setDraftImage(null);
    setDraftEmail(null);
    setSaving(false);
    notify.success({ title: "个人资料已保存" });
    await session.refetch();
  }

  if (session.isPending) return <p className={styles.state}>正在加载账号信息...</p>;
  if (!user) return <p className={styles.state}>请先登录。</p>;

  return (
    <div className={styles.page}>
      <PageHeader title="个人账号" description="管理个人资料、账号安全和额度" />
      <AccountSettingsNav />
      <form className={styles.panel} onSubmit={save}>
        <div className={styles.panelHeading}>
          <UserRound size={22} aria-hidden="true" />
          <div><h2>个人资料</h2><p>用户名是唯一登录标识，目前不支持修改。</p></div>
        </div>
        <div className={styles.avatarRow}>
          <InitialAvatar name={avatarLabel} image={image} size={88} />
          <div><strong>头像</strong><p>填写图片链接后可以预览头像。</p><span className={styles.hint}><Camera size={14} aria-hidden="true" /> 支持 HTTPS 图片地址</span></div>
        </div>
        <div className={styles.fields}>
          <TextInput label="用户名" value={username} leadingVisual={AtSign} readOnly block />
          <TextInput label="电子邮箱" value={email} onChange={(event) => setDraftEmail(event.currentTarget.value)} type="email" leadingVisual={Mail} required block />
          <TextInput className={styles.fullField} label="头像链接" value={image} onChange={(event) => setDraftImage(event.currentTarget.value)} placeholder="https://..." block />
        </div>
        <div className={styles.footer}><span /><Button type="submit" variant="primary" leadingVisual={Save} disabled={saving}>{saving ? "正在保存" : "保存"}</Button></div>
      </form>
    </div>
  );
}
