import { createHash, randomBytes, randomUUID } from "node:crypto";
import { createAuthEndpoint } from "@better-auth/core/api";
import { runWithTransaction } from "@better-auth/core/context";
import type { BetterAuthPlugin } from "better-auth";
import { z } from "zod";
import { betterAuthDatabase } from "./better-auth-database";

const invitationBody = z.object({
  token: z.string().min(32),
  password: z.string().min(12).max(128),
});

type InvitationRole = "admin" | "user";

type InvitationRow = {
  id: string;
  tokenHash: string;
  email: string;
  name: string;
  role: InvitationRole;
  initialDailySuccessLimit: number;
  createdByUserId: string;
  createdAt: string;
  expiresAt: string;
  consumedAt: string | null;
  consumedUserId: string | null;
  workspaceProvisionedAt: string | null;
  revokedAt: string | null;
  revokedByUserId: string | null;
};

// The custom table uses synchronous better-sqlite3 statements inside Better Auth's
// async transaction. Serialize redemption within the single frontend process so a
// competing request cannot block the event loop while the first transaction awaits.
let invitationMutationTail = Promise.resolve();

async function withInvitationMutation<T>(operation: () => Promise<T>): Promise<T> {
  const previous = invitationMutationTail;
  let release!: () => void;
  invitationMutationTail = new Promise<void>((resolve) => { release = resolve; });
  await previous;
  try {
    return await operation();
  } finally {
    release();
  }
}

export type InvitationRecord = Omit<InvitationRow, "tokenHash"> & {
  status: "pending" | "consumed" | "revoked" | "expired";
};

function tokenHash(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

function generateInvitationCode(): string {
  const value = randomBytes(20).toString("hex").toUpperCase();
  return value.match(/.{1,5}/g)?.join("-") || value;
}

function normalizeEmail(email: string): string {
  const normalized = email.trim().toLowerCase();
  if (!z.string().email().safeParse(normalized).success) throw new Error("email 格式无效");
  return normalized;
}

function invitationStatus(row: InvitationRow, now = new Date()): InvitationRecord["status"] {
  if (row.consumedAt) return "consumed";
  if (row.revokedAt) return "revoked";
  if (new Date(row.expiresAt) <= now) return "expired";
  return "pending";
}

function publicInvitation(row: InvitationRow): InvitationRecord {
  const { tokenHash: _tokenHash, ...record } = row;
  return { ...record, status: invitationStatus(row) };
}

export function recordAuthAudit(input: {
  actorUserId: string;
  action: string;
  targetUserId?: string | null;
  invitationId?: string | null;
  metadata?: Record<string, unknown>;
}): void {
  betterAuthDatabase.prepare(
    `insert into "oopsnote_auth_audit" (
       "id", "actorUserId", "action", "targetUserId", "invitationId", "metadataJson", "createdAt"
     ) values (?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    randomUUID(),
    input.actorUserId,
    input.action,
    input.targetUserId ?? null,
    input.invitationId ?? null,
    JSON.stringify(input.metadata ?? {}),
    new Date().toISOString(),
  );
}

export async function createInvitation(input: {
  email: string;
  name: string;
  role: InvitationRole;
  createdByUserId: string;
  initialDailySuccessLimit?: number;
  expiresInHours?: number;
}): Promise<{ id: string; code: string; expiresAt: Date }> {
  const email = normalizeEmail(input.email);
  const name = input.name.trim();
  if (!name || name.length > 128) throw new Error("name 必须为 1 到 128 个字符");
  const initialDailySuccessLimit = Math.trunc(input.initialDailySuccessLimit ?? 20);
  if (initialDailySuccessLimit < 0 || initialDailySuccessLimit > 1_000_000) {
    throw new Error("初始每日额度必须在 0 到 1000000 之间");
  }
  const existingUser = betterAuthDatabase
    .prepare('select 1 from "user" where "email" = ? limit 1')
    .get(email);
  if (existingUser) throw new Error("该邮箱已经注册");

  const id = randomUUID();
  // This displayed code still contains 160 bits of entropy. Only its hash is stored.
  const code = generateInvitationCode();
  const createdAt = new Date();
  const expiresAt = new Date(createdAt.getTime() + Math.max(1, input.expiresInHours ?? 72) * 60 * 60 * 1000);
  const create = betterAuthDatabase.transaction(() => {
    const superseded = betterAuthDatabase.prepare(
      `select * from "oopsnote_invitation"
       where "email" = ? and "consumedAt" is null and "revokedAt" is null and "expiresAt" > ?`,
    ).all(email, createdAt.toISOString()) as InvitationRow[];
    betterAuthDatabase.prepare(
      `update "oopsnote_invitation"
       set "revokedAt" = ?, "revokedByUserId" = ?
       where "email" = ? and "consumedAt" is null and "revokedAt" is null and "expiresAt" > ?`,
    ).run(createdAt.toISOString(), input.createdByUserId, email, createdAt.toISOString());
    for (const invitation of superseded) {
      recordAuthAudit({
        actorUserId: input.createdByUserId,
        action: "invitation.superseded",
        invitationId: invitation.id,
      });
    }
    betterAuthDatabase.prepare(
      `insert into "oopsnote_invitation" (
         "id", "tokenHash", "email", "name", "role", "initialDailySuccessLimit", "createdByUserId", "createdAt", "expiresAt"
       ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(
      id,
      tokenHash(code),
      email,
      name,
      input.role,
      initialDailySuccessLimit,
      input.createdByUserId,
      createdAt.toISOString(),
      expiresAt.toISOString(),
    );
    recordAuthAudit({
      actorUserId: input.createdByUserId,
      action: "invitation.created",
      invitationId: id,
      metadata: { email, role: input.role, initialDailySuccessLimit, expiresAt: expiresAt.toISOString() },
    });
  });
  create();
  return { id, code, expiresAt };
}

export function listInvitations(limit = 100): InvitationRecord[] {
  const safeLimit = Math.min(Math.max(Math.trunc(limit), 1), 100);
  const rows = betterAuthDatabase.prepare(
    'select * from "oopsnote_invitation" order by "createdAt" desc limit ?',
  ).all(safeLimit) as InvitationRow[];
  return rows.map(publicInvitation);
}

export function revokeInvitation(invitationId: string, actorUserId: string): InvitationRecord | null {
  const now = new Date().toISOString();
  const revoke = betterAuthDatabase.transaction(() => {
    const result = betterAuthDatabase.prepare(
      `update "oopsnote_invitation"
       set "revokedAt" = ?, "revokedByUserId" = ?
       where "id" = ? and "consumedAt" is null and "revokedAt" is null and "expiresAt" > ?`,
    ).run(now, actorUserId, invitationId, now);
    if (result.changes !== 1) return null;
    recordAuthAudit({ actorUserId, action: "invitation.revoked", invitationId });
    return betterAuthDatabase
      .prepare('select * from "oopsnote_invitation" where "id" = ?')
      .get(invitationId) as InvitationRow;
  });
  const row = revoke();
  return row ? publicInvitation(row) : null;
}

export function pendingInitialQuota(userId: string): number | null {
  const row = betterAuthDatabase.prepare(
    `select "initialDailySuccessLimit" from "oopsnote_invitation"
     where "consumedUserId" = ? and "workspaceProvisionedAt" is null
     order by "consumedAt" desc limit 1`,
  ).get(userId) as { initialDailySuccessLimit: number } | undefined;
  return row ? Number(row.initialDailySuccessLimit) : null;
}

export function markWorkspaceProvisioned(userId: string): void {
  betterAuthDatabase.prepare(
    `update "oopsnote_invitation" set "workspaceProvisionedAt" = ?
     where "consumedUserId" = ? and "workspaceProvisionedAt" is null`,
  ).run(new Date().toISOString(), userId);
}

export const betterAuthInvitationPlugin: BetterAuthPlugin = {
  id: "oopsnote-invitations",
  version: "2.0.0",
  endpoints: {
    redeemInvitation: createAuthEndpoint("/invite/redeem", {
      method: "POST",
      body: invitationBody,
    }, async (ctx) => {
      const { token, password } = ctx.body;
      return withInvitationMutation(() => runWithTransaction(ctx.context.adapter, async () => {
        const now = new Date().toISOString();
        const invitation = betterAuthDatabase
          .prepare('select * from "oopsnote_invitation" where "tokenHash" = ? limit 1')
          .get(tokenHash(token)) as InvitationRow | undefined;
        if (!invitation || invitationStatus(invitation, new Date(now)) !== "pending") {
          throw ctx.error("BAD_REQUEST", { message: "邀请链接无效或已过期" });
        }
        if (await ctx.context.internalAdapter.findUserByEmail(invitation.email)) {
          throw ctx.error("BAD_REQUEST", { message: "该邮箱已经注册" });
        }
        const claimed = betterAuthDatabase.prepare(
          `update "oopsnote_invitation" set "consumedAt" = ?
           where "id" = ? and "consumedAt" is null and "revokedAt" is null and "expiresAt" > ?`,
        ).run(now, invitation.id, now);
        if (claimed.changes !== 1) {
          throw ctx.error("BAD_REQUEST", { message: "邀请链接无效或已过期" });
        }
        const user = await ctx.context.internalAdapter.createUser({
          email: invitation.email,
          name: invitation.name,
          role: invitation.role,
          emailVerified: false,
        });
        const hashedPassword = await ctx.context.password.hash(password);
        await ctx.context.internalAdapter.linkAccount({
          accountId: user.id,
          providerId: "credential",
          userId: user.id,
          password: hashedPassword,
        });
        betterAuthDatabase.prepare(
          'update "oopsnote_invitation" set "consumedUserId" = ? where "id" = ?',
        ).run(user.id, invitation.id);
        recordAuthAudit({
          actorUserId: user.id,
          action: "invitation.consumed",
          targetUserId: user.id,
          invitationId: invitation.id,
        });
        return ctx.json({ user });
      }));
    }),
  },
};
