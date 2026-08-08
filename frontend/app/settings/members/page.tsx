"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useReducedMotion } from "@/components/ui/primitives";
import { Ban, Check, Copy, KeyRound, LoaderCircle, RefreshCcw, RotateCcw, ShieldAlert, Ticket, UserPlus, UsersRound } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import { InitialAvatar } from "@/components/ui/InitialAvatar";
import { Button, Collapse, IconButton, Modal, PasswordInput, Select, TextInput } from "@/components/ui/primitives";
import { fetchJson } from "@/lib/api";
import { isAdminUser } from "@/lib/auth";
import { notify } from "@/lib/notify";
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
  username?: string | null;
  displayUsername?: string | null;
  email: string;
  image?: string | null;
  role?: string | null;
  banned?: boolean | null;
  createdAt: string;
  quota: MemberQuota;
  provisioningPending: boolean;
};

type Invitation = {
  id: string;
  maxUses: number;
  useCount: number;
  initialDailySuccessLimit: number;
  expiresAt: string;
  status: "active" | "exhausted" | "revoked" | "expired";
};

type MembersResponse = {
  users: Member[];
  invitations: Invitation[];
  quotaAvailable: boolean;
};

function defaultExpiry(): string {
  const expires = new Date(Date.now() + 72 * 60 * 60 * 1000);
  const local = new Date(expires.getTime() - expires.getTimezoneOffset() * 60 * 1000);
  return local.toISOString().slice(0, 16);
}

export default function MembersPage() {
  const { user, loading: authLoading } = useAuth();
  const reducedMotion = useReducedMotion();
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [quotaAvailable, setQuotaAvailable] = useState(true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [invitationModalOpen, setInvitationModalOpen] = useState(false);
  const [createdInvitation, setCreatedInvitation] = useState<{ code: string; url: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/admin/members", { cache: "no-store" });
      const payload = await response.json() as MembersResponse & { error?: string };
      if (!response.ok) throw new Error(payload.error || "无法加载成员列表");
      setMembers(payload.users);
      setInvitations(payload.invitations || []);
      setQuotaAvailable(payload.quotaAvailable);
    } catch (reason) {
      notify.error({ title: "成员加载失败", description: reason instanceof Error ? reason.message : "无法加载成员列表" });
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
    setBusy("create-user");
    try {
      const response = await fetch("/api/admin/members", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          kind: "user",
          username: form.get("username"),
          email: form.get("email"),
          password: form.get("password"),
          dailySuccessLimit: form.get("dailySuccessLimit"),
        }),
      });
      const payload = await response.json() as { error?: string; workspaceProvisioned?: boolean };
      if (!response.ok) throw new Error(payload.error || "创建用户失败");
      event.currentTarget.reset();
      setShowCreateForm(false);
      notify.success({
        title: "用户已创建",
        description: payload.workspaceProvisioned === false ? "额度将在用户首次访问时自动初始化。" : undefined,
      });
      await load();
    } catch (reason) {
      notify.error({ title: "创建失败", description: reason instanceof Error ? reason.message : "创建用户失败" });
    } finally {
      setBusy(null);
    }
  }

  async function createInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("create-invitation");
    try {
      const response = await fetch("/api/admin/members", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          kind: "invitation",
          maxUses: form.get("maxUses"),
          expiresAt: new Date(String(form.get("expiresAt"))).toISOString(),
          dailySuccessLimit: form.get("dailySuccessLimit"),
        }),
      });
      const payload = await response.json() as { error?: string; invitationCode?: string; invitationUrl?: string };
      if (!response.ok || !payload.invitationCode || !payload.invitationUrl) throw new Error(payload.error || "生成邀请码失败");
      setCreatedInvitation({ code: payload.invitationCode, url: `${window.location.origin}${payload.invitationUrl}` });
      notify.success({ title: "邀请码已生成" });
      await load();
    } catch (reason) {
      notify.error({ title: "生成失败", description: reason instanceof Error ? reason.message : "生成邀请码失败" });
    } finally {
      setBusy(null);
    }
  }

  async function memberAction(member: Member, action: "ban" | "unban" | "revoke-sessions" | "set-role", role?: string) {
    setBusy(`${member.id}:${action}`);
    try {
      const response = await fetch("/api/admin/members", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ userId: member.id, action, role }),
      });
      const payload = await response.json() as { error?: string };
      if (!response.ok) throw new Error(payload.error || "成员操作失败");
      notify.success({ title: action === "revoke-sessions" ? "登录会话已撤销" : "成员信息已更新" });
      await load();
    } catch (reason) {
      notify.error({ title: "操作失败", description: reason instanceof Error ? reason.message : "成员操作失败" });
    } finally {
      setBusy(null);
    }
  }

  async function updateQuota(member: Member, value: string) {
    const daily = Number(value);
    if (!Number.isInteger(daily) || daily < 0) {
      notify.error({ title: "每日额度必须是非负整数" });
      return;
    }
    setBusy(`${member.id}:quota`);
    try {
      await fetchJson(`/admin/members/${encodeURIComponent(member.id)}/quota`, { method: "PATCH", body: JSON.stringify({ daily_success_limit: daily }) });
      notify.success({ title: "成员额度已更新" });
      await load();
    } catch (reason) {
      notify.error({ title: "额度更新失败", description: reason instanceof Error ? reason.message : "额度更新失败" });
    } finally {
      setBusy(null);
    }
  }

  async function revokeInvitation(invitation: Invitation) {
    setBusy(`${invitation.id}:revoke-invitation`);
    try {
      const response = await fetch("/api/admin/members", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "revoke-invitation", invitationId: invitation.id }),
      });
      const payload = await response.json() as { error?: string };
      if (!response.ok) throw new Error(payload.error || "撤销邀请失败");
      notify.success({ title: "邀请码已撤销" });
      await load();
    } catch (reason) {
      notify.error({ title: "撤销失败", description: reason instanceof Error ? reason.message : "撤销邀请失败" });
    } finally {
      setBusy(null);
    }
  }

  if (!authLoading && !isAdminUser(user)) return <p><ShieldAlert size={18} /> 成员管理仅管理员可用。</p>;

  return (
    <div className={styles.page}>
      <PageHeader
        title="成员"
        description="管理用户、管理员权限和每日 AI 额度"
        action={(
          <div className={styles.headerActions}>
            <Button type="button" variant="secondary" leadingVisual={Ticket} onClick={() => { setCreatedInvitation(null); setInvitationModalOpen(true); }}>生成邀请码</Button>
            <Button type="button" variant="primary" leadingVisual={UserPlus} onClick={() => setShowCreateForm((visible) => !visible)}>{showCreateForm ? "收起" : "添加用户"}</Button>
          </div>
        )}
      />

      <Collapse expanded={showCreateForm} transitionDuration={reducedMotion ? 0 : 180}>
        <section className={styles.panel}>
          <div className={styles.panelHeading}><UserPlus size={22} aria-hidden="true" /><div><h2>添加用户</h2><p>直接创建的账号固定为用户角色，之后可以在成员列表中提升为管理员。</p></div></div>
          <form className={styles.toolbar} onSubmit={createMember}>
            <TextInput className={styles.field} label="用户名" name="username" minLength={3} maxLength={32} pattern="[A-Za-z0-9_.]+" autoComplete="off" required />
            <TextInput className={styles.field} label="邮箱" name="email" type="email" autoComplete="off" required />
            <PasswordInput className={styles.field} label="初始密码" name="password" minLength={12} maxLength={128} autoComplete="new-password" required />
            <TextInput className={styles.field} label="每日额度" name="dailySuccessLimit" type="number" min="0" max="1000000" defaultValue="20" required />
            <Button type="submit" variant="primary" leadingVisual={busy === "create-user" ? LoaderCircle : UserPlus} disabled={busy === "create-user"}>创建用户</Button>
          </form>
        </section>
      </Collapse>

      <section className={styles.panel}>
        <div className={styles.panelHeading}><UsersRound size={22} aria-hidden="true" /><div><h2>管理成员</h2><p>{loading ? "正在同步成员信息..." : `共 ${members.length} 位成员`}</p></div></div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead><tr><th>成员</th><th>状态</th><th>角色</th><th>今日额度</th><th>并发</th><th>加入时间</th><th>操作</th></tr></thead>
            <tbody>
              {members.map((member) => {
                const isBusy = busy?.startsWith(`${member.id}:`) || false;
                const isCurrentUser = member.id === user?.subject;
                const displayName = member.displayUsername || member.username || member.name;
                const quotaLabel = member.provisioningPending ? "等待首次访问" : quotaAvailable ? "未建立" : "暂不可用";
                return (
                  <tr key={member.id}>
                    <td><div className={styles.memberIdentity}><InitialAvatar name={displayName} image={member.image} size={32} /><div className={styles.identity}><strong>{displayName}</strong><span>{member.email}</span></div></div></td>
                    <td><span className={`${styles.status}${member.banned ? ` ${styles.statusBanned}` : ""}`}><span className={styles.statusDot} />{member.banned ? "已禁用" : "可用"}</span></td>
                    <td><Select className={styles.role} aria-label={`${displayName} 的角色`} value={member.role || "user"} disabled={isBusy || isCurrentUser} onValueChange={(value) => void memberAction(member, "set-role", value)}><Select.Option value="user">用户</Select.Option><Select.Option value="admin">管理员</Select.Option></Select></td>
                    <td>{member.quota ? <div className={styles.quota}><span>{member.quota.used_units} /</span><TextInput aria-label={`${member.email} 每日额度`} type="number" min="0" defaultValue={member.quota.daily_success_limit} onBlur={(event) => void updateQuota(member, event.target.value)} /></div> : quotaLabel}</td>
                    <td>{member.quota ? `${member.quota.active_runs} / ${member.quota.max_concurrent_runs}` : "-"}</td>
                    <td>{new Date(member.createdAt).toLocaleDateString("zh-CN")}</td>
                    <td><div className={styles.actions}>
                      <IconButton className={styles.iconButton} type="button" aria-label="撤销全部会话" title="撤销全部会话" icon={RefreshCcw} disabled={isBusy} onClick={() => void memberAction(member, "revoke-sessions")} />
                      <IconButton className={styles.iconButton} type="button" aria-label={member.banned ? "恢复账号" : "禁用账号"} title={isCurrentUser ? "不能禁用当前管理员" : member.banned ? "恢复账号" : "禁用账号"} icon={member.banned ? RotateCcw : Ban} disabled={isBusy || isCurrentUser} onClick={() => void memberAction(member, member.banned ? "unban" : "ban")} />
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

      <section className={styles.panel}>
        <div className={styles.panelHeading}><Ticket size={22} aria-hidden="true" /><div><h2>邀请码</h2><p>邀请码按次数、有效期和每位用户的额度进行限制。</p></div></div>
        <div className={styles.tableWrap}>
          <table className={`${styles.table} ${styles.invitationTable}`}>
            <thead><tr><th>使用次数</th><th>每人每日额度</th><th>状态</th><th>有效期</th><th>操作</th></tr></thead>
            <tbody>
              {invitations.map((invitation) => {
                const label = invitation.status === "active" ? "有效" : invitation.status === "exhausted" ? "已用完" : invitation.status === "revoked" ? "已撤销" : "已过期";
                const isBusy = busy === `${invitation.id}:revoke-invitation`;
                return <tr key={invitation.id}><td>{invitation.useCount} / {invitation.maxUses}</td><td>{invitation.initialDailySuccessLimit}</td><td>{label}</td><td>{new Date(invitation.expiresAt).toLocaleString("zh-CN")}</td><td>{invitation.status === "active" && <IconButton type="button" aria-label="撤销邀请码" title="撤销邀请码" icon={Ban} disabled={isBusy} onClick={() => void revokeInvitation(invitation)} />}</td></tr>;
              })}
              {!loading && invitations.length === 0 && <tr><td colSpan={5}>暂无邀请码</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <Modal opened={invitationModalOpen} onClose={() => setInvitationModalOpen(false)} title="生成邀请码" centered size="md">
        {createdInvitation ? (
          <div className={styles.invitationResult}>
            <label>邀请码<code>{createdInvitation.code}</code></label>
            <div className={styles.modalActions}><Button type="button" variant="secondary" leadingVisual={Copy} onClick={() => { void navigator.clipboard.writeText(createdInvitation.code); notify.success({ title: "邀请码已复制" }); }}>复制邀请码</Button><Button type="button" variant="primary" leadingVisual={Copy} onClick={() => { void navigator.clipboard.writeText(createdInvitation.url); notify.success({ title: "注册链接已复制" }); }}>复制注册链接</Button></div>
          </div>
        ) : (
          <form className={styles.modalForm} onSubmit={createInvitation}>
            <TextInput className={styles.field} label="使用次数" name="maxUses" type="number" min="1" max="100" defaultValue="1" required />
            <TextInput className={styles.field} label="过期时间" name="expiresAt" type="datetime-local" defaultValue={defaultExpiry()} required />
            <TextInput className={styles.field} label="每位用户每日额度" name="dailySuccessLimit" type="number" min="0" max="1000000" defaultValue="20" required />
            <div className={styles.roleSummary}><KeyRound size={16} aria-hidden="true" /><span>通过邀请码注册的账号固定为“用户”角色。</span></div>
            <div className={styles.modalActions}><Button type="button" variant="secondary" onClick={() => setInvitationModalOpen(false)}>取消</Button><Button type="submit" variant="primary" leadingVisual={busy === "create-invitation" ? LoaderCircle : Ticket} disabled={busy === "create-invitation"}>生成</Button></div>
          </form>
        )}
      </Modal>
    </div>
  );
}
