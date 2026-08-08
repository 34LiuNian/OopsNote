import fs from "node:fs";
import { randomUUID } from "node:crypto";
import { NextResponse } from "next/server";
import { auth, betterAuthIdentityStats } from "@/lib/better-auth";
import { recordAuthAudit } from "@/lib/better-auth-invitations";
import { betterAuthDatabase } from "@/lib/better-auth-database";
import { runWithTransaction } from "@better-auth/core/context";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function bootstrapSecret(): string {
  const file = process.env.OOPSNOTE_BOOTSTRAP_SECRET_FILE?.trim();
  if (file) return fs.readFileSync(file, "utf8").trim();
  return process.env.OOPSNOTE_BOOTSTRAP_SECRET?.trim() || "";
}

export async function POST(request: Request) {
  const configured = bootstrapSecret();
  const supplied = request.headers.get("x-oopsnote-bootstrap-secret")?.trim() || "";
  if (!configured || supplied.length < 32 || supplied !== configured) {
    return NextResponse.json({ error: "bootstrap secret 无效" }, { status: 404 });
  }
  try {
    const body = await request.json() as { email?: unknown; name?: unknown; password?: unknown };
    const email = typeof body.email === "string" ? body.email.trim() : "";
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const password = typeof body.password === "string" ? body.password : "";
    if (!email || !name || password.length < 12) {
      return NextResponse.json({ error: "email、name 和至少 12 位密码为必填项" }, { status: 400 });
    }
    const context = await auth.$context;
    const hashedPassword = await context.password.hash(password);
    const claimToken = randomUUID();
    const claimedAt = new Date();
    const staleBefore = new Date(claimedAt.getTime() - 10 * 60 * 1000).toISOString();
    const claimBootstrap = betterAuthDatabase.transaction(() => {
      if (betterAuthIdentityStats().totalUsers !== 0) {
        throw Object.assign(new Error("管理员已初始化，bootstrap 已关闭"), { status: 409 });
      }
      const claimed = betterAuthDatabase.prepare(
        `update "oopsnote_bootstrap_state"
         set "claimToken" = ?, "claimedAt" = ?
         where "id" = 1
           and "completedAt" is null
           and ("claimToken" is null or "claimedAt" < ?)
           and not exists (select 1 from "user")`,
      ).run(claimToken, claimedAt.toISOString(), staleBefore);
      if (claimed.changes !== 1) {
        throw Object.assign(new Error("管理员初始化正在进行或已经完成"), { status: 409 });
      }
    });
    claimBootstrap();

    let result: { user: Awaited<ReturnType<typeof context.internalAdapter.createUser>> };
    try {
      result = await runWithTransaction(context.adapter, async () => {
      if (await context.internalAdapter.findUserByEmail(email)) {
        throw Object.assign(new Error("该邮箱已经注册"), { status: 409 });
      }
      const user = await context.internalAdapter.createUser({
        email,
        name,
        role: "admin",
        emailVerified: false,
      });
      await context.internalAdapter.linkAccount({
        accountId: user.id,
        providerId: "credential",
        userId: user.id,
        password: hashedPassword,
      });
      return { user };
      });
    } catch (error) {
      if (betterAuthIdentityStats().totalUsers === 0) {
        betterAuthDatabase.prepare(
          `update "oopsnote_bootstrap_state"
           set "claimToken" = null, "claimedAt" = null
           where "id" = 1 and "claimToken" = ? and "completedAt" is null`,
        ).run(claimToken);
      }
      throw error;
    }

    const finalizeBootstrap = betterAuthDatabase.transaction(() => {
      const finalized = betterAuthDatabase.prepare(
        `update "oopsnote_bootstrap_state"
         set "completedAt" = ?, "claimToken" = null, "claimedAt" = null
         where "id" = 1 and "claimToken" = ? and "completedAt" is null`,
      ).run(new Date().toISOString(), claimToken);
      if (finalized.changes !== 1) throw new Error("bootstrap 状态提交失败");
      recordAuthAudit({ actorUserId: result.user.id, action: "bootstrap.admin_created", targetUserId: result.user.id });
    });
    finalizeBootstrap();
    return NextResponse.json({ user: result.user }, { status: 201 });
  } catch (error) {
    const candidate = error as { message?: string; status?: number; statusCode?: number } | null;
    const message = candidate?.message || "bootstrap 失败";
    const status = Number(candidate?.statusCode || candidate?.status || 500);
    return NextResponse.json({ error: message }, { status: status >= 400 && status < 600 ? status : 500 });
  }
}
