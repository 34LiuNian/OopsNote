import { createHash, randomBytes, randomUUID } from "node:crypto";
import { createAuthEndpoint } from "@better-auth/core/api";
import { runWithTransaction } from "@better-auth/core/context";
import type { BetterAuthPlugin } from "better-auth";
import { z } from "zod";
import { betterAuthDatabase } from "./better-auth-database";
import {
  getRegistrationPolicy,
  normalizeEmail,
  normalizeUsername,
  queueUserProvisioning,
} from "./better-auth-registration";

const registerBody = z.object({
  username: z.string().min(3).max(32),
  email: z.string().email(),
  password: z.string().min(12).max(128),
  invitationCode: z.string().max(128).optional(),
});

type InvitationRow = {
  id: string;
  tokenHash: string;
  maxUses: number;
  useCount: number;
  initialDailySuccessLimit: number;
  createdByUserId: string;
  createdAt: string;
  expiresAt: string;
  revokedAt: string | null;
  revokedByUserId: string | null;
};

let registrationMutationTail = Promise.resolve();

async function withRegistrationMutation<T>(operation: () => Promise<T>): Promise<T> {
  const previous = registrationMutationTail;
  let release!: () => void;
  registrationMutationTail = new Promise<void>((resolve) => { release = resolve; });
  await previous;
  try {
    return await operation();
  } finally {
    release();
  }
}

export type InvitationRecord = Omit<InvitationRow, "tokenHash"> & {
  status: "active" | "exhausted" | "revoked" | "expired";
};

function tokenHash(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

function generateInvitationCode(): string {
  const value = randomBytes(20).toString("hex").toUpperCase();
  return value.match(/.{1,5}/g)?.join("-") || value;
}

function invitationStatus(row: InvitationRow, now = new Date()): InvitationRecord["status"] {
  if (row.revokedAt) return "revoked";
  if (new Date(row.expiresAt) <= now) return "expired";
  if (Number(row.useCount) >= Number(row.maxUses)) return "exhausted";
  return "active";
}

function publicInvitation(row: InvitationRow): InvitationRecord {
  const { tokenHash: _tokenHash, ...record } = row;
  return {
    ...record,
    maxUses: Number(row.maxUses),
    useCount: Number(row.useCount),
    initialDailySuccessLimit: Number(row.initialDailySuccessLimit),
    status: invitationStatus(row),
  };
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

export function createInvitation(input: {
  createdByUserId: string;
  maxUses: number;
  expiresAt: Date;
  initialDailySuccessLimit: number;
}): { id: string; code: string; expiresAt: Date } {
  const maxUses = Math.trunc(input.maxUses);
  const initialDailySuccessLimit = Math.trunc(input.initialDailySuccessLimit);
  if (maxUses < 1 || maxUses > 100) throw new Error("邀请码使用次数必须在 1 到 100 之间");
  if (initialDailySuccessLimit < 0 || initialDailySuccessLimit > 1_000_000) {
    throw new Error("每日额度必须在 0 到 1000000 之间");
  }
  const createdAt = new Date();
  if (!Number.isFinite(input.expiresAt.getTime()) || input.expiresAt <= createdAt) {
    throw new Error("邀请码过期时间必须晚于当前时间");
  }
  if (input.expiresAt.getTime() > createdAt.getTime() + 365 * 24 * 60 * 60 * 1000) {
    throw new Error("邀请码有效期不能超过一年");
  }

  const id = randomUUID();
  const code = generateInvitationCode();
  betterAuthDatabase.transaction(() => {
    betterAuthDatabase.prepare(
      `insert into "oopsnote_invitation" (
         "id", "tokenHash", "maxUses", "useCount", "initialDailySuccessLimit",
         "createdByUserId", "createdAt", "expiresAt"
       ) values (?, ?, ?, 0, ?, ?, ?, ?)`,
    ).run(
      id,
      tokenHash(code),
      maxUses,
      initialDailySuccessLimit,
      input.createdByUserId,
      createdAt.toISOString(),
      input.expiresAt.toISOString(),
    );
    recordAuthAudit({
      actorUserId: input.createdByUserId,
      action: "invitation.created",
      invitationId: id,
      metadata: { maxUses, initialDailySuccessLimit, expiresAt: input.expiresAt.toISOString() },
    });
  })();
  return { id, code, expiresAt: input.expiresAt };
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
       where "id" = ? and "revokedAt" is null and "expiresAt" > ? and "useCount" < "maxUses"`,
    ).run(now, actorUserId, invitationId, now);
    if (result.changes !== 1) return null;
    recordAuthAudit({ actorUserId, action: "invitation.revoked", invitationId });
    return betterAuthDatabase.prepare(
      'select * from "oopsnote_invitation" where "id" = ?',
    ).get(invitationId) as InvitationRow;
  });
  const row = revoke();
  return row ? publicInvitation(row) : null;
}

export const betterAuthInvitationPlugin: BetterAuthPlugin = {
  id: "oopsnote-registration",
  version: "3.0.0",
  endpoints: {
    registrationPolicy: createAuthEndpoint("/registration-policy", { method: "GET" }, async (ctx) => {
      const policy = getRegistrationPolicy();
      return ctx.json({ mode: policy.mode });
    }),
    registerUser: createAuthEndpoint("/register", {
      method: "POST",
      body: registerBody,
    }, async (ctx) => {
      const username = normalizeUsername(ctx.body.username);
      const displayUsername = ctx.body.username.trim();
      const email = normalizeEmail(ctx.body.email);
      const invitationCode = ctx.body.invitationCode?.trim() || null;
      return withRegistrationMutation(() => runWithTransaction(ctx.context.adapter, async () => {
        const policy = getRegistrationPolicy();
        if (policy.mode === "closed") {
          throw ctx.error("FORBIDDEN", { message: "当前未开放注册" });
        }
        if (policy.mode === "invite" && !invitationCode) {
          throw ctx.error("BAD_REQUEST", { message: "请输入有效的邀请码" });
        }
        if (await ctx.context.internalAdapter.findUserByEmail(email)) {
          throw ctx.error("BAD_REQUEST", { message: "该邮箱已经注册" });
        }
        const existingUsername = betterAuthDatabase.prepare(
          'select 1 from "user" where "username" = ? limit 1',
        ).get(username);
        if (existingUsername) throw ctx.error("BAD_REQUEST", { message: "该用户名已被使用" });

        let invitation: InvitationRow | null = null;
        let dailySuccessLimit = policy.openDailySuccessLimit;
        if (invitationCode) {
          invitation = betterAuthDatabase.prepare(
            'select * from "oopsnote_invitation" where "tokenHash" = ? limit 1',
          ).get(tokenHash(invitationCode)) as InvitationRow | undefined || null;
          if (!invitation || invitationStatus(invitation) !== "active") {
            throw ctx.error("BAD_REQUEST", { message: "邀请码无效、已用完或已过期" });
          }
          dailySuccessLimit = Number(invitation.initialDailySuccessLimit);
          const claimed = betterAuthDatabase.prepare(
            `update "oopsnote_invitation" set "useCount" = "useCount" + 1
             where "id" = ? and "revokedAt" is null and "expiresAt" > ? and "useCount" < "maxUses"`,
          ).run(invitation.id, new Date().toISOString());
          if (claimed.changes !== 1) {
            throw ctx.error("BAD_REQUEST", { message: "邀请码无效、已用完或已过期" });
          }
        } else if (policy.mode !== "open") {
          throw ctx.error("BAD_REQUEST", { message: "请输入有效的邀请码" });
        }

        const user = await ctx.context.internalAdapter.createUser({
          email,
          emailVerified: false,
          name: displayUsername,
          username,
          displayUsername,
          role: "user",
        });
        const hashedPassword = await ctx.context.password.hash(ctx.body.password);
        await ctx.context.internalAdapter.linkAccount({
          accountId: user.id,
          providerId: "credential",
          userId: user.id,
          password: hashedPassword,
        });
        queueUserProvisioning({
          userId: user.id,
          dailySuccessLimit,
          source: invitation ? "invitation" : "open",
        });
        if (invitation) {
          betterAuthDatabase.prepare(
            `insert into "oopsnote_invitation_redemption" ("id", "invitationId", "userId", "createdAt")
             values (?, ?, ?, ?)`,
          ).run(randomUUID(), invitation.id, user.id, new Date().toISOString());
        }
        recordAuthAudit({
          actorUserId: user.id,
          action: invitation ? "invitation.redeemed" : "registration.open",
          targetUserId: user.id,
          invitationId: invitation?.id,
          metadata: { username, email, dailySuccessLimit },
        });
        return ctx.json({ user });
      }));
    }),
  },
};
