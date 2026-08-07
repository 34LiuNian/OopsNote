import { z } from "zod";
import { betterAuthDatabase } from "./better-auth-database";

export type RegistrationMode = "closed" | "invite" | "open";
export type ProvisioningSource = "invitation" | "open" | "admin";

export type PendingProvisioning = {
  dailySuccessLimit: number;
  preserveExistingQuota: boolean;
};

export type RegistrationPolicy = {
  mode: RegistrationMode;
  openDailySuccessLimit: number;
  updatedAt: string;
  updatedByUserId: string | null;
};

const reservedUsernames = new Set(["admin", "root", "system", "oopsnote", "support"]);

export function normalizeEmail(value: string): string {
  const email = value.trim().toLowerCase();
  if (!z.string().email().safeParse(email).success) throw new Error("邮箱格式无效");
  return email;
}

export function normalizeUsername(value: string): string {
  const username = value.trim().toLowerCase();
  if (username.length < 3 || username.length > 32) throw new Error("用户名必须为 3 到 32 个字符");
  if (!/^[a-zA-Z0-9_.]+$/.test(username)) throw new Error("用户名只能包含字母、数字、下划线和点");
  if (reservedUsernames.has(username)) throw new Error("该用户名不可使用");
  return username;
}

export function getRegistrationPolicy(): RegistrationPolicy {
  const row = betterAuthDatabase.prepare(
    `select "mode", "openDailySuccessLimit", "updatedAt", "updatedByUserId"
     from "oopsnote_registration_policy" where "id" = 1`,
  ).get() as RegistrationPolicy | undefined;
  if (!row) throw new Error("注册策略尚未初始化");
  return { ...row, openDailySuccessLimit: Number(row.openDailySuccessLimit) };
}

export function updateRegistrationPolicy(input: {
  mode: RegistrationMode;
  openDailySuccessLimit: number;
  actorUserId: string;
}): RegistrationPolicy {
  const dailyLimit = Math.trunc(input.openDailySuccessLimit);
  if (!(["closed", "invite", "open"] as const).includes(input.mode)) throw new Error("注册模式无效");
  if (dailyLimit < 0 || dailyLimit > 1_000_000) throw new Error("开放注册每日额度必须在 0 到 1000000 之间");
  betterAuthDatabase.prepare(
    `update "oopsnote_registration_policy"
     set "mode" = ?, "openDailySuccessLimit" = ?, "updatedAt" = ?, "updatedByUserId" = ?
     where "id" = 1`,
  ).run(input.mode, dailyLimit, new Date().toISOString(), input.actorUserId);
  return getRegistrationPolicy();
}

export function queueUserProvisioning(input: {
  userId: string;
  dailySuccessLimit: number;
  source: ProvisioningSource;
}): void {
  const dailyLimit = Math.trunc(input.dailySuccessLimit);
  if (dailyLimit < 0 || dailyLimit > 1_000_000) throw new Error("每日额度必须在 0 到 1000000 之间");
  betterAuthDatabase.prepare(
    `insert into "oopsnote_user_provisioning" (
       "userId", "dailySuccessLimit", "source", "createdAt", "provisionedAt", "preserveExistingQuota"
     ) values (?, ?, ?, ?, null, 0)
     on conflict("userId") do update set
       "dailySuccessLimit" = excluded."dailySuccessLimit",
       "source" = excluded."source",
       "provisionedAt" = null,
       "preserveExistingQuota" = 0`,
  ).run(input.userId, dailyLimit, input.source, new Date().toISOString());
}

export function pendingInitialQuota(userId: string): number | null {
  return pendingProvisioning(userId)?.dailySuccessLimit ?? null;
}

export function pendingProvisioning(userId: string): PendingProvisioning | null {
  const row = betterAuthDatabase.prepare(
    `select "dailySuccessLimit", "preserveExistingQuota" from "oopsnote_user_provisioning"
     where "userId" = ? and "provisionedAt" is null`,
  ).get(userId) as { dailySuccessLimit: number; preserveExistingQuota: number } | undefined;
  return row
    ? { dailySuccessLimit: Number(row.dailySuccessLimit), preserveExistingQuota: row.preserveExistingQuota === 1 }
    : null;
}

export function markWorkspaceProvisioned(userId: string): void {
  betterAuthDatabase.prepare(
    `update "oopsnote_user_provisioning" set "provisionedAt" = ?
     where "userId" = ? and "provisionedAt" is null`,
  ).run(new Date().toISOString(), userId);
}
