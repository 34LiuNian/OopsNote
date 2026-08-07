import { NextResponse } from "next/server";
import { auth, betterAuthIdentityStats } from "@/lib/better-auth";
import { signInternalIdentity } from "@/lib/internal-identity";
import { createInvitation, listInvitations, recordAuthAudit, revokeInvitation } from "@/lib/better-auth-invitations";
import { withAdminGate } from "@/lib/better-auth-admin-gate";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type MemberAction = "ban" | "unban" | "set-role" | "revoke-sessions" | "revoke-invitation";

function errorResponse(error: unknown): NextResponse {
  const candidate = error as { status?: number; statusCode?: number; message?: string } | null;
  const status = Number(candidate?.statusCode || candidate?.status || 500);
  const lastAdminViolation = candidate?.message?.includes("OOPSNOTE_LAST_ACTIVE_ADMIN") === true;
  const safeStatus = lastAdminViolation ? 409 : status >= 400 && status < 600 ? status : 500;
  return NextResponse.json(
    { error: lastAdminViolation ? "不能移除最后一个可用管理员" : candidate?.message || "管理操作失败" },
    { status: safeStatus },
  );
}

async function requireAdmin(request: Request): Promise<NonNullable<Awaited<ReturnType<typeof auth.api.getSession>>>> {
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) throw Object.assign(new Error("未登录"), { status: 401 });
  const role = session.user.role;
  if (role !== "admin" && !(Array.isArray(role) && role.includes("admin"))) {
    throw Object.assign(new Error("需要管理员权限"), { status: 403 });
  }
  return session;
}

async function backendAdminRequest(
  session: Awaited<ReturnType<typeof requireAdmin>>,
  path: string,
  method: "POST" | "PATCH",
  body: unknown,
): Promise<unknown> {
  const backendUrl = (process.env.OOPSNOTE_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const identity = signInternalIdentity({
    userId: session.user.id,
    role: "admin",
    method,
    path,
  });
  const response = await fetch(`${backendUrl}${path}`, {
    method,
    headers: {
      "content-type": "application/json",
      "x-oopsnote-identity": identity.encoded,
      "x-oopsnote-signature": identity.signature,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Backend member request failed: ${response.status}`);
  return response.json();
}

export async function GET(request: Request) {
  try {
    const session = await requireAdmin(request);
    const url = new URL(request.url);
    const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || 50), 1), 100);
    const offset = Math.max(Number(url.searchParams.get("offset") || 0), 0);
    const searchValue = url.searchParams.get("searchValue") || undefined;
    const result = await auth.api.listUsers({
      headers: request.headers,
      query: { limit, offset, searchValue },
    });
    let summaries: Record<string, unknown> = {};
    try {
      const summary = await backendAdminRequest(
        session,
        "/admin/members/summary",
        "POST",
        { auth_user_ids: result.users.map((user) => user.id) },
      ) as { members?: Record<string, unknown> };
      summaries = summary.members || {};
    } catch (error) {
      console.warn("Unable to load member quota summaries", error);
    }
    return NextResponse.json({
      ...result,
      users: result.users.map((user) => ({ ...user, quota: summaries[user.id] || null })),
      invitations: listInvitations(),
    });
  } catch (error) {
    return errorResponse(error);
  }
}

export async function POST(request: Request) {
  try {
    const session = await requireAdmin(request);
    const body = await request.json() as {
      email?: unknown;
      name?: unknown;
      password?: unknown;
      role?: unknown;
      invitation?: unknown;
      daily_success_limit?: unknown;
    };
    const email = typeof body.email === "string" ? body.email.trim() : "";
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const password = typeof body.password === "string" ? body.password : "";
    const role = body.role === "admin" ? "admin" : "user";
    const dailySuccessLimit = body.daily_success_limit === undefined || body.daily_success_limit === ""
      ? 20
      : Number(body.daily_success_limit);
    if (!Number.isInteger(dailySuccessLimit) || dailySuccessLimit < 0 || dailySuccessLimit > 1_000_000) {
      return NextResponse.json({ error: "每日额度必须是 0 到 1000000 的整数" }, { status: 400 });
    }
    if (body.invitation === true) {
      if (!email || !name) return NextResponse.json({ error: "email 和 name 为必填项" }, { status: 400 });
      const invitation = await createInvitation({ email, name, role, createdByUserId: session.user.id, initialDailySuccessLimit: dailySuccessLimit, expiresInHours: 72 });
      return NextResponse.json({ invitationUrl: `/invite?token=${encodeURIComponent(invitation.token)}`, expiresAt: invitation.expiresAt }, { status: 201 });
    }
    if (!email || !name || password.length < 12) {
      return NextResponse.json({ error: "email、name 和至少 12 位密码为必填项" }, { status: 400 });
    }
    const result = await auth.api.createUser({
      headers: withAdminGate(request.headers),
      body: { email, name, password, role },
    });
    recordAuthAudit({ actorUserId: session.user.id, action: "user.created", targetUserId: result.user.id, metadata: { role } });
    let workspaceProvisioned = false;
    try {
      await backendAdminRequest(
        session,
        "/admin/members/provision",
        "POST",
        { auth_user_id: result.user.id, daily_success_limit: dailySuccessLimit },
      );
      workspaceProvisioned = true;
    } catch (error) {
      console.warn("Member was created but workspace provisioning is pending", error);
    }
    return NextResponse.json({ ...result, workspaceProvisioned }, { status: 201 });
  } catch (error) {
    return errorResponse(error);
  }
}

export async function PATCH(request: Request) {
  try {
    const session = await requireAdmin(request);
    const body = await request.json() as {
      userId?: unknown;
      invitationId?: unknown;
      action?: unknown;
      role?: unknown;
      banReason?: unknown;
    };
    const userId = typeof body.userId === "string" ? body.userId.trim() : "";
    const action = body.action as MemberAction;
    const invitationId = typeof body.invitationId === "string" ? body.invitationId.trim() : "";
    if (action === "revoke-invitation") {
      if (!invitationId) return NextResponse.json({ error: "invitationId 无效" }, { status: 400 });
      const invitation = revokeInvitation(invitationId, session.user.id);
      if (!invitation) return NextResponse.json({ error: "邀请不存在、已使用、已撤销或已过期" }, { status: 409 });
      return NextResponse.json({ invitation });
    }
    if (!userId || !["ban", "unban", "set-role", "revoke-sessions"].includes(action)) {
      return NextResponse.json({ error: "userId 或 action 无效" }, { status: 400 });
    }
    if (userId === session.user.id && (action === "ban" || action === "set-role") && body.role !== "admin") {
      return NextResponse.json({ error: "不能禁用或降级当前管理员" }, { status: 400 });
    }
    if (action === "set-role" || action === "ban") {
      const stats = betterAuthIdentityStats();
      const target = await auth.api.getUser({ headers: request.headers, query: { id: userId } });
      const targetRole = target.role;
      const isTargetAdmin = targetRole === "admin" || (Array.isArray(targetRole) && targetRole.includes("admin"));
      const demotingLastAdmin = action === "set-role" && body.role !== "admin" && isTargetAdmin && !target.banned && stats.activeAdminUsers <= 1;
      const banningLastAdmin = action === "ban" && isTargetAdmin && !target.banned && stats.activeAdminUsers <= 1;
      if (demotingLastAdmin || banningLastAdmin) {
        return NextResponse.json({ error: "不能移除最后一个可用管理员" }, { status: 409 });
      }
    }
    if (action === "ban") {
      const result = await auth.api.banUser({
        headers: withAdminGate(request.headers),
        body: { userId, banReason: typeof body.banReason === "string" ? body.banReason : undefined },
      });
      recordAuthAudit({ actorUserId: session.user.id, action: "user.banned", targetUserId: userId });
      return NextResponse.json(result);
    }
    if (action === "unban") {
      const result = await auth.api.unbanUser({ headers: withAdminGate(request.headers), body: { userId } });
      recordAuthAudit({ actorUserId: session.user.id, action: "user.unbanned", targetUserId: userId });
      return NextResponse.json(result);
    }
    if (action === "revoke-sessions") {
      const result = await auth.api.revokeUserSessions({ headers: withAdminGate(request.headers), body: { userId } });
      recordAuthAudit({ actorUserId: session.user.id, action: "user.sessions_revoked", targetUserId: userId });
      return NextResponse.json(result);
    }
    const role = body.role === "admin" ? "admin" : body.role === "user" ? "user" : null;
    if (!role) return NextResponse.json({ error: "role 必须是 admin 或 user" }, { status: 400 });
    const result = await auth.api.setRole({ headers: withAdminGate(request.headers), body: { userId, role } });
    recordAuthAudit({ actorUserId: session.user.id, action: "user.role_changed", targetUserId: userId, metadata: { role } });
    return NextResponse.json(result);
  } catch (error) {
    return errorResponse(error);
  }
}
