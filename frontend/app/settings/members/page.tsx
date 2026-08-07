"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Ban, Check, LoaderCircle, Plus, RefreshCcw, RotateCcw, ShieldAlert } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import { isAdminUser } from "@/lib/auth";
import { fetchJson } from "@/lib/api";
import styles from "./members.module.css";

type MemberQuota = {
  daily_success_limit: number;
  max_concurrent_runs: number;
  active_runs: number;
  used_units: number;
} | null;

type Member = {
  id: string;
  name: string;
  email: string;
  role?: string | null;
  banned?: boolean | null;
  createdAt: string;
  quota: MemberQuota;
};

type Invitation = {
  id: string;
  email: string;
  name: string;
  role: string;
  initialDailySuccessLimit: number;
  createdAt: string;
  expiresAt: string;
  consumedUserId?: string | null;
  workspaceProvisionedAt?: string | null;
  status: "pending" | "consumed" | "revoked" | "expired";
};

type MembersResponse = { users: Member[]; total: number; invitations: Invitation[] };

export default function MembersPage() {
  const { user, loading: authLoading } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [invitationUrl, setInvitationUrl] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/admin/members", { cache: "no-store" });
      if (!response.ok) throw new Error("无法加载成员列表");
      const payload = await response.json() as MembersResponse;
      setMembers(payload.users);
      setInvitations(payload.invitations || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法加载成员列表");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Loading is an external request; its async state transitions belong in load().
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!authLoading && isAdminUser(user)) void load();
  }, [authLoading, load, user]);

  async function createMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const intent = ((event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null)?.value || "create";
    setBusy("create");
    setError("");
    setMessage("");
    setInvitationUrl("");
    try {
      const response = await fetch("/api/admin/members", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: form.get("name"), email: form.get("email"), password: form.get("password"), role: form.get("role"), daily_success_limit: form.get("daily_success_limit"), invitation: intent === "invite" }),
      });
      const payload = await response.json() as { error?: string; workspaceProvisioned?: boolean; invitationUrl?: string };
      if (!response.ok) throw new Error(payload.error || "创建成员失败");
      event.currentTarget.reset();
      if (payload.invitationUrl) {
        setInvitationUrl(`${window.location.origin}${payload.invitationUrl}`);
        setMessage("邀请已创建，72 小时内有效。");
      } else {
        setMessage(payload.workspaceProvisioned === false ? "账号已创建，工作区将在首次登录时自动初始化。" : "内测账号已创建。");
      }
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建成员失败");
    } finally {
      setBusy(null);
    }
  }

  async function memberAction(member: Member, action: "ban" | "unban" | "revoke-sessions" | "set-role", role?: string) {
    setBusy(`${member.id}:${action}`);
    setError("");
    try {
      const response = await fetch("/api/admin/members", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ userId: member.id, action, role }),
      });
      const payload = await response.json() as { error?: string };
      if (!response.ok) throw new Error(payload.error || "成员操作失败");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "成员操作失败");
    } finally {
      setBusy(null);
    }
  }

  async function updateQuota(member: Member, value: string) {
    const daily = Number(value);
    if (!Number.isInteger(daily) || daily < 0) {
      setError("每日额度必须是非负整数");
      return;
    }
    setBusy(`${member.id}:quota`);
    setError("");
    try {
      await fetchJson(`/admin/members/${encodeURIComponent(member.id)}/quota`, { method: "PATCH", body: JSON.stringify({ daily_success_limit: daily }) });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "额度更新失败");
    } finally {
      setBusy(null);
    }
  }

  async function revokeInvitation(invitation: Invitation) {
    setBusy(`${invitation.id}:revoke-invitation`);
    setError("");
    try {
      const response = await fetch("/api/admin/members", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "revoke-invitation", invitationId: invitation.id }),
      });
      const payload = await response.json() as { error?: string };
      if (!response.ok) throw new Error(payload.error || "撤销邀请失败");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "撤销邀请失败");
    } finally {
      setBusy(null);
    }
  }

  if (!authLoading && !isAdminUser(user)) return <p><ShieldAlert size={18} /> 成员管理仅管理员可用。</p>;

  return (
    <div className={styles.page}>
      <PageHeader title="内测成员" description="管理登录账号、状态、角色和每日 AI 额度" />
      <form className={styles.toolbar} onSubmit={createMember}>
        <label className={styles.field}>显示名<input name="name" required /></label>
        <label className={styles.field}>邮箱<input name="email" type="email" required /></label>
        <label className={styles.field}>初始密码（直接创建时）<input name="password" type="password" minLength={12} /></label>
        <label className={styles.field}>角色<select name="role" defaultValue="user"><option value="user">使用者</option><option value="admin">管理员</option></select></label>
        <label className={styles.field}>初始每日额度<input name="daily_success_limit" type="number" min="0" max="1000000" defaultValue="20" required /></label>
        <button className={styles.command} type="submit" name="intent" value="invite" disabled={busy === "create"}>{busy === "create" ? <LoaderCircle size={16} className="oops-login-spinner" /> : <Plus size={16} />}创建邀请</button>
        <button className={`${styles.command} ${styles.primary}`} type="submit" name="intent" value="create" disabled={busy === "create"}>直接创建</button>
      </form>
      {(message || error) && <p className={`${styles.message}${error ? ` ${styles.messageError}` : ""}`}>{error || message}</p>}
      {invitationUrl && <p className={styles.message}><code>{invitationUrl}</code> <button className={styles.command} type="button" onClick={() => void navigator.clipboard.writeText(invitationUrl)}>复制链接</button></p>}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead><tr><th>成员</th><th>状态</th><th>角色</th><th>今日额度</th><th>并发</th><th>加入时间</th><th>操作</th></tr></thead>
          <tbody>
            {members.map((member) => {
              const isBusy = busy?.startsWith(`${member.id}:`) || false;
              return <tr key={member.id}>
                <td><div className={styles.identity}><strong>{member.name}</strong><span>{member.email}</span></div></td>
                <td><span className={`${styles.status}${member.banned ? ` ${styles.statusBanned}` : ""}`}><span className={styles.statusDot} />{member.banned ? "已禁用" : "可用"}</span></td>
                <td><select className={styles.role} value={member.role || "user"} disabled={isBusy} onChange={(event) => void memberAction(member, "set-role", event.target.value)}><option value="user">使用者</option><option value="admin">管理员</option></select></td>
                <td>{member.quota ? <div className={styles.quota}><span>{member.quota.used_units} /</span><input aria-label={`${member.email} 每日额度`} type="number" min="0" defaultValue={member.quota.daily_success_limit} onBlur={(event) => void updateQuota(member, event.target.value)} /></div> : "待初始化"}</td>
                <td>{member.quota ? `${member.quota.active_runs} / ${member.quota.max_concurrent_runs}` : "-"}</td>
                <td>{new Date(member.createdAt).toLocaleDateString("zh-CN")}</td>
                <td><div className={styles.actions}>
                  <button className={styles.iconButton} type="button" title="撤销全部会话" disabled={isBusy} onClick={() => void memberAction(member, "revoke-sessions")}><RefreshCcw size={15} /></button>
                  <button className={styles.iconButton} type="button" title={member.banned ? "恢复账号" : "禁用账号"} disabled={isBusy} onClick={() => void memberAction(member, member.banned ? "unban" : "ban")}>{member.banned ? <RotateCcw size={15} /> : <Ban size={15} />}</button>
                  {!isBusy && <Check size={14} aria-hidden="true" />}
                </div></td>
              </tr>;
            })}
            {!loading && members.length === 0 && <tr><td colSpan={7}>暂无成员</td></tr>}
          </tbody>
        </table>
      </div>
      {invitations.length > 0 && <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead><tr><th>待处理邀请</th><th>角色</th><th>初始额度</th><th>状态</th><th>有效期</th><th>操作</th></tr></thead>
          <tbody>{invitations.map((invitation) => {
            const isBusy = busy === `${invitation.id}:revoke-invitation`;
            return <tr key={invitation.id}>
              <td><div className={styles.identity}><strong>{invitation.name}</strong><span>{invitation.email}</span></div></td>
              <td>{invitation.role === "admin" ? "管理员" : "使用者"}</td>
              <td>{invitation.initialDailySuccessLimit}</td>
              <td>{invitation.status === "pending" ? "待兑换" : invitation.status === "consumed" ? "已兑换" : invitation.status === "revoked" ? "已撤销" : "已过期"}</td>
              <td>{new Date(invitation.expiresAt).toLocaleString("zh-CN")}</td>
              <td>{invitation.status === "pending" && <button className={styles.iconButton} type="button" title="撤销邀请" disabled={isBusy} onClick={() => void revokeInvitation(invitation)}><Ban size={15} /></button>}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
      {loading && <p className={styles.message}>正在加载成员…</p>}
    </div>
  );
}
