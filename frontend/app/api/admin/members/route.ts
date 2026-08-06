import { NextResponse } from "next/server";
import { auth, betterAuthIdentityStats } from "@/lib/better-auth";
import { signInternalIdentity } from "@/lib/internal-identity";
import { createInvitation } from "@/lib/better-auth-invitations";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type MemberAction = "ban" | "unban" | "set-role" | "revoke-sessions";

function errorResponse(error: unknown): NextResponse {
  const candidate = error as { status?: number; statusCode?: number; message?: string } | null;
  const status = Number(candidate?.statusCode || candidate?.status || 500);
  const safeStatus = status >= 400 && status < 600 ? status : 500;
  return NextResponse.json(
    { error: candidate?.message || "管理操作失败" },
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
    };
    const email = typeof body.email === "string" ? body.email.trim() : "";
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const password = typeof body.password === "string" ? body.password : "";
    const role = body.role === "admin" ? "admin" : "user";
    if (body.invitation === true) {
      if (!email || !name) return NextResponse.json({ error: "email 和 name 为必填项" }, { status: 400 });
      const invitation = await createInvitation({ email, name, role, expiresInHours: 72 });
      return NextResponse.json({ invitationUrl: `/invite?token=${encodeURIComponent(invitation.token)}`, expiresAt: invitation.expiresAt }, { status: 201 });
    }
    if (!email || !name || password.length < 12) {
      return NextResponse.json({ error: "email、name 和至少 12 位密码为必填项" }, { status: 400 });
    }
    const result = await auth.api.createUser({
      headers: request.headers,
      body: { email, name, password, role },
    });
    let workspaceProvisioned = false;
    try {
      await backendAdminRequest(
        session,
        "/admin/members/provision",
        "POST",
        { auth_user_id: result.user.id },
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
      action?: unknown;
      role?: unknown;
      banReason?: unknown;
    };
    const userId = typeof body.userId === "string" ? body.userId.trim() : "";
    const action = body.action as MemberAction;
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
      const demotingLastAdmin = action === "set-role" && body.role !== "admin" && isTargetAdmin && stats.adminUsers <= 1;
      const banningLastAdmin = action === "ban" && isTargetAdmin && stats.adminUsers <= 1;
      if (demotingLastAdmin || banningLastAdmin) {
        return NextResponse.json({ error: "不能移除最后一个可用管理员" }, { status: 409 });
      }
    }
    if (action === "ban") {
      return NextResponse.json(await auth.api.banUser({
        headers: request.headers,
        body: { userId, banReason: typeof body.banReason === "string" ? body.banReason : undefined },
      }));
    }
    if (action === "unban") {
      return NextResponse.json(await auth.api.unbanUser({ headers: request.headers, body: { userId } }));
    }
    if (action === "revoke-sessions") {
      return NextResponse.json(await auth.api.revokeUserSessions({ headers: request.headers, body: { userId } }));
    }
    const role = body.role === "admin" ? "admin" : body.role === "user" ? "user" : null;
    if (!role) return NextResponse.json({ error: "role 必须是 admin 或 user" }, { status: 400 });
    return NextResponse.json(await auth.api.setRole({ headers: request.headers, body: { userId, role } }));
  } catch (error) {
    return errorResponse(error);
  }
}
