import fs from "node:fs";
import { randomUUID } from "node:crypto";
import { auth } from "@/lib/better-auth";
import { recordAuthAudit } from "@/lib/better-auth-invitations";
import { betterAuthDatabase, betterAuthIdentityStats } from "@/lib/better-auth-database";
import { runWithTransaction } from "@better-auth/core/context";

/** 服务端 bootstrap 密钥（secret 文件优先，其次环境变量）。 */
export function bootstrapSecret(): string {
  const file = process.env.OOPSNOTE_BOOTSTRAP_SECRET_FILE?.trim();
  if (file) return fs.readFileSync(file, "utf8").trim();
  return process.env.OOPSNOTE_BOOTSTRAP_SECRET?.trim() || "";
}

export type BootstrapAdminInput = { email: string; name: string; password: string };

/**
 * 原子地创建第一个管理员（Better Auth 唯一身份真源）。
 * 约束：必须配置 bootstrap 密钥；用户表必须为空；claim 与创建均为一次性。
 */
export async function bootstrapAdmin(input: BootstrapAdminInput): Promise<{ userId: string }> {
  if (!bootstrapSecret()) {
    throw Object.assign(new Error("未配置 bootstrap 密钥"), { status: 404 });
  }
  const email = input.email.trim();
  const name = input.name.trim();
  const password = input.password;
  if (!email || !name || password.length < 12) {
    throw Object.assign(new Error("email、name 和至少 12 位密码为必填项"), { status: 400 });
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

  let userId: string;
  try {
    const result = await runWithTransaction(context.adapter, async () => {
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
      return user;
    });
    userId = result.id;
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
    recordAuthAudit({ actorUserId: userId, action: "bootstrap.admin_created", targetUserId: userId });
  });
  finalizeBootstrap();
  return { userId };
}
