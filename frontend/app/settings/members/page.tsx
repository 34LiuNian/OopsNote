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

type MembersResponse = { users: Member[]; total: number };

export default function MembersPage() {
  const { user, loading: authLoading } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/admin/members", { cache: "no-store" });
      if (!response.ok) throw new Error("无法加载成员列表");
      const payload = await response.json() as MembersResponse;
      setMembers(payload.users);
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
    setBusy("create");
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/admin/members", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: form.get("name"), email: form.get("email"), password: form.get("password"), role: form.get("role") }),
      });
      const payload = await response.json() as { error?: string; workspaceProvisioned?: boolean };
      if (!response.ok) throw new Error(payload.error || "创建成员失败");
      event.currentTarget.reset();
      setMessage(payload.workspaceProvisioned === false ? "账号已创建，工作区将在首次登录时自动初始化。" : "内测账号已创建。");
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

  if (!authLoading && !isAdminUser(user)) return <p><ShieldAlert size={18} /> 成员管理仅管理员可用。</p>;

  return (
    <div className={styles.page}>
      <PageHeader title="内测成员" description="管理登录账号、状态、角色和每日 AI 额度" />
      <form className={styles.toolbar} onSubmit={createMember}>
        <label className={styles.field}>显示名<input name="name" required /></label>
        <label className={styles.field}>邮箱<input name="email" type="email" required /></label>
        <label className={styles.field}>初始密码<input name="password" type="password" minLength={12} required /></label>
        <label className={styles.field}>角色<select name="role" defaultValue="user"><option value="user">使用者</option><option value="admin">管理员</option></select></label>
        <button className={`${styles.command} ${styles.primary}`} type="submit" disabled={busy === "create"}>{busy === "create" ? <LoaderCircle size={16} className="oops-login-spinner" /> : <Plus size={16} />}创建账号</button>
      </form>
      {(message || error) && <p className={`${styles.message}${error ? ` ${styles.messageError}` : ""}`}>{error || message}</p>}
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
      {loading && <p className={styles.message}>正在加载成员…</p>}
    </div>
  );
}
