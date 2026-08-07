"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Ban, Check, Copy, LoaderCircle, Plus, RefreshCcw, RotateCcw, ShieldAlert, UserPlus, UsersRound } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import { InitialAvatar } from "@/components/ui/InitialAvatar";
import { Button, IconButton } from "@/components/ui/primitives";
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
  image?: string | null;
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
  expiresAt: string;
  status: "pending" | "consumed" | "revoked" | "expired";
};

type MembersResponse = { users: Member[]; invitations: Invitation[] };

export default function MembersPage() {
  const { user, loading: authLoading } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [invitationUrl, setInvitationUrl] = useState("");
  const [invitationCode, setInvitationCode] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);

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
    // Member loading is an external request; its state transitions are owned by load().
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
    setInvitationCode("");
    try {
      const response = await fetch("/api/admin/members", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: form.get("name"),
          email: form.get("email"),
          password: form.get("password"),
          role: form.get("role"),
          daily_success_limit: form.get("daily_success_limit"),
          invitation: intent === "invite",
        }),
      });
      const payload = await response.json() as {
        error?: string;
        workspaceProvisioned?: boolean;
        invitationUrl?: string;
        invitationCode?: string;
      };
      if (!response.ok) throw new Error(payload.error || "创建成员失败");
      event.currentTarget.reset();
      if (payload.invitationUrl) {
        setInvitationUrl(`${window.location.origin}${payload.invitationUrl}`);
        setInvitationCode(payload.invitationCode || "");
        setMessage("邀请码已创建，72 小时内有效。");
      } else {
        setMessage(payload.workspaceProvisioned === false ? "账号已创建，工作区将在首次登录时自动初始化。" : "内测账号已创建。");
      }
      setShowCreateForm(false);
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
      await fetchJson(`/admin/members/${encodeURIComponent(member.id)}/quota`, {
        method: "PATCH",
        body: JSON.stringify({ daily_success_limit: daily }),
      });
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

  if (!authLoading && !isAdminUser(user)) {
    return <p><ShieldAlert size={18} /> 成员管理仅管理员可用。</p>;
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title="成员管理"
        description="管理角色、访问状态与每日 AI 额度"
        action={(
          <Button type="button" variant="primary" leadingVisual={UserPlus} onClick={() => setShowCreateForm((visible) => !visible)}>
            {showCreateForm ? "收起表单" : "添加用户"}
          </Button>
        )}
      />

      {showCreateForm && (
        <section className={styles.panel}>
          <div className={styles.panelHeading}>
            <UserPlus size={22} aria-hidden="true" />
            <div><h2>创建成员</h2><p>邀请成员自行设置密码，或直接创建内部测试账号。</p></div>
          </div>
          <form className={styles.toolbar} onSubmit={createMember}>
            <label className={styles.field}>显示名<input name="name" required /></label>
            <label className={styles.field}>邮箱<input name="email" type="email" required /></label>
            <label className={styles.field}>初始密码（直接创建时）<input name="password" type="password" minLength={12} /></label>
            <label className={styles.field}>角色<select name="role" defaultValue="user"><option value="user">使用者</option><option value="admin">管理员</option></select></label>
            <label className={styles.field}>初始每日额度<input name="daily_success_limit" type="number" min="0" max="1000000" defaultValue="20" required /></label>
            <Button className={styles.command} type="submit" name="intent" value="invite" variant="secondary" leadingVisual={busy === "create" ? LoaderCircle : Plus} disabled={busy === "create"}>创建邀请</Button>
            <Button className={`${styles.command} ${styles.primary}`} type="submit" name="intent" value="create" variant="primary" leadingVisual={UserPlus} disabled={busy === "create"}>直接创建</Button>
          </form>
        </section>
      )}

      {(message || error) && <p className={`${styles.message}${error ? ` ${styles.messageError}` : ""}`}>{error || message}</p>}
      {invitationUrl && (
        <div className={styles.message}>
          <code>邀请码：{invitationCode}</code>{" "}
          <Button type="button" variant="secondary" leadingVisual={Copy} onClick={() => void navigator.clipboard.writeText(invitationUrl)}>复制注册链接</Button>
        </div>
      )}

      <section className={styles.panel}>
        <div className={styles.panelHeading}>
          <UsersRound size={22} aria-hidden="true" />
          <div><h2>管理成员</h2><p>{loading ? "正在同步成员信息..." : `共 ${members.length} 位成员`}</p></div>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead><tr><th>成员</th><th>状态</th><th>角色</th><th>今日额度</th><th>并发</th><th>加入时间</th><th>操作</th></tr></thead>
            <tbody>
              {members.map((member) => {
                const isBusy = busy?.startsWith(`${member.id}:`) || false;
                return (
                  <tr key={member.id}>
                    <td><div className={styles.memberIdentity}><InitialAvatar name={member.name} image={member.image} size={32} /><div className={styles.identity}><strong>{member.name}</strong><span>{member.email}</span></div></div></td>
                    <td><span className={`${styles.status}${member.banned ? ` ${styles.statusBanned}` : ""}`}><span className={styles.statusDot} />{member.banned ? "已禁用" : "可用"}</span></td>
                    <td><select className={styles.role} value={member.role || "user"} disabled={isBusy} onChange={(event) => void memberAction(member, "set-role", event.target.value)}><option value="user">使用者</option><option value="admin">管理员</option></select></td>
                    <td>{member.quota ? <div className={styles.quota}><span>{member.quota.used_units} /</span><input aria-label={`${member.email} 每日额度`} type="number" min="0" defaultValue={member.quota.daily_success_limit} onBlur={(event) => void updateQuota(member, event.target.value)} /></div> : "待初始化"}</td>
                    <td>{member.quota ? `${member.quota.active_runs} / ${member.quota.max_concurrent_runs}` : "-"}</td>
                    <td>{new Date(member.createdAt).toLocaleDateString("zh-CN")}</td>
                    <td><div className={styles.actions}>
                      <IconButton className={styles.iconButton} type="button" aria-label="撤销全部会话" title="撤销全部会话" icon={RefreshCcw} disabled={isBusy} onClick={() => void memberAction(member, "revoke-sessions")} />
                      <IconButton className={styles.iconButton} type="button" aria-label={member.banned ? "恢复账户" : "禁用账户"} title={member.banned ? "恢复账户" : "禁用账户"} icon={member.banned ? RotateCcw : Ban} disabled={isBusy} onClick={() => void memberAction(member, member.banned ? "unban" : "ban")} />
                      {!isBusy && <Check size={14} aria-hidden="true" />}
                    </div></td>
                  </tr>
                );
              })}
              {!loading && members.length === 0 && <tr><td colSpan={7}>暂无成员</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {invitations.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead><tr><th>待处理邀请</th><th>角色</th><th>初始额度</th><th>状态</th><th>有效期</th><th>操作</th></tr></thead>
            <tbody>{invitations.map((invitation) => {
              const isBusy = busy === `${invitation.id}:revoke-invitation`;
              const status = invitation.status === "pending" ? "待兑换" : invitation.status === "consumed" ? "已兑换" : invitation.status === "revoked" ? "已撤销" : "已过期";
              return (
                <tr key={invitation.id}>
                  <td><div className={styles.identity}><strong>{invitation.name}</strong><span>{invitation.email}</span></div></td>
                  <td>{invitation.role === "admin" ? "管理员" : "使用者"}</td>
                  <td>{invitation.initialDailySuccessLimit}</td>
                  <td>{status}</td>
                  <td>{new Date(invitation.expiresAt).toLocaleString("zh-CN")}</td>
                  <td>{invitation.status === "pending" && <IconButton className={styles.iconButton} type="button" aria-label="撤销邀请" title="撤销邀请" icon={Ban} disabled={isBusy} onClick={() => void revokeInvitation(invitation)} />}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      )}
      {loading && <p className={styles.message}>正在加载成员...</p>}
    </div>
  );
}
