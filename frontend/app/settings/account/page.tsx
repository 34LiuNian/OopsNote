"use client";

import { useMemo, useState } from "react";
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
  const [saving, setSaving] = useState<"email" | "avatar" | null>(null);

  const username = identity?.displayUsername || identity?.username || identity?.name || "";
  const image = draftImage ?? user?.image ?? "";
  const email = draftEmail ?? user?.email ?? "";
  const currentEmail = user?.email ?? "";
  const currentImage = user?.image ?? "";
  const avatarLabel = useMemo(() => username || email || "OopsNote", [email, username]);

  async function saveAvatar() {
    setSaving("avatar");
    try {
      const profileResult = await authClient.updateUser({ image: image.trim() || null });
      if (profileResult.error) throw new Error(profileResult.error.message);
      setDraftImage(null);
      await session.refetch();
      notify.success({ title: "头像已保存" });
    } catch (reason) {
      notify.error({ title: "头像保存失败", description: reason instanceof Error ? reason.message : "请稍后重试" });
    } finally {
      setSaving(null);
    }
  }

  async function saveEmail() {
    setSaving("email");
    try {
      const emailResult = await authClient.changeEmail({ newEmail: email.trim(), callbackURL: "/settings/account" });
      if (emailResult.error) throw new Error(emailResult.error.message);
      setDraftEmail(null);
      await session.refetch();
      notify.success({ title: "邮箱已更新" });
    } catch (reason) {
      notify.error({ title: "邮箱更新失败", description: reason instanceof Error ? reason.message : "请稍后重试" });
    } finally {
      setSaving(null);
    }
  }

  if (session.isPending) return <p className={styles.state}>正在加载账号信息...</p>;
  if (!user) return <p className={styles.state}>请先登录。</p>;

  return (
    <div className={styles.page}>
      <PageHeader title="个人账号" description="管理个人资料、账号安全和额度" />
      <AccountSettingsNav />
      <section className={styles.panel}>
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
        <div className={styles.footer}>
          <Button type="button" variant="secondary" leadingVisual={Save} disabled={saving !== null || email.trim().toLowerCase() === currentEmail.toLowerCase()} onClick={() => void saveEmail()}>{saving === "email" ? "正在更新邮箱" : "更新邮箱"}</Button>
          <Button type="button" variant="primary" leadingVisual={Save} disabled={saving !== null || image.trim() === currentImage} onClick={() => void saveAvatar()}>{saving === "avatar" ? "正在保存头像" : "保存头像"}</Button>
        </div>
      </section>
    </div>
  );
}
