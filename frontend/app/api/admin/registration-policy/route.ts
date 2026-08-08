import { NextResponse } from "next/server";
import { auth } from "@/lib/better-auth";
import { recordAuthAudit } from "@/lib/better-auth-invitations";
import { getRegistrationPolicy, updateRegistrationPolicy, type RegistrationMode } from "@/lib/better-auth-registration";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function requireAdmin(request: Request) {
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) throw Object.assign(new Error("未登录"), { status: 401 });
  const role = session.user.role;
  if (role !== "admin" && !(Array.isArray(role) && role.includes("admin"))) {
    throw Object.assign(new Error("需要管理员权限"), { status: 403 });
  }
  return session;
}

function errorResponse(error: unknown) {
  const candidate = error as { status?: number; message?: string };
  return NextResponse.json(
    { error: candidate?.message || "注册策略操作失败" },
    { status: candidate?.status && candidate.status >= 400 ? candidate.status : 500 },
  );
}

export async function GET(request: Request) {
  try {
    await requireAdmin(request);
    return NextResponse.json(getRegistrationPolicy());
  } catch (error) {
    return errorResponse(error);
  }
}

export async function PUT(request: Request) {
  try {
    const session = await requireAdmin(request);
    const body = await request.json() as { mode?: unknown; openDailySuccessLimit?: unknown };
    const mode = body.mode as RegistrationMode;
    const openDailySuccessLimit = Number(body.openDailySuccessLimit);
    const policy = updateRegistrationPolicy({ mode, openDailySuccessLimit, actorUserId: session.user.id });
    recordAuthAudit({
      actorUserId: session.user.id,
      action: "registration_policy.updated",
      metadata: { mode: policy.mode, openDailySuccessLimit: policy.openDailySuccessLimit },
    });
    return NextResponse.json(policy);
  } catch (error) {
    return errorResponse(error);
  }
}
