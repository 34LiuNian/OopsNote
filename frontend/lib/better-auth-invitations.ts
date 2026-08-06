import { createHash, randomBytes } from "node:crypto";
import { createAuthEndpoint } from "@better-auth/core/api";
import { runWithTransaction } from "@better-auth/core/context";
import type { BetterAuthPlugin } from "better-auth";
import { z } from "zod";

const INVITE_PREFIX = "oopsnote-invite:";
const invitationBody = z.object({
  token: z.string().min(32),
  password: z.string().min(12),
});

type InvitationPayload = {
  email: string;
  name: string;
  role: "admin" | "user";
};

function tokenHash(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export function invitationIdentifier(token: string): string {
  return `${INVITE_PREFIX}${tokenHash(token)}`;
}

export async function createInvitation(input: InvitationPayload & { expiresInHours?: number }): Promise<{ token: string; expiresAt: Date }> {
  const token = randomBytes(32).toString("base64url");
  const expiresAt = new Date(Date.now() + Math.max(1, input.expiresInHours ?? 72) * 60 * 60 * 1000);
  const { auth } = await import("@/lib/better-auth");
  const context = await auth.$context;
  await context.internalAdapter.createVerificationValue({
    identifier: invitationIdentifier(token),
    value: JSON.stringify({ email: input.email.trim().toLowerCase(), name: input.name.trim(), role: input.role }),
    expiresAt,
  });
  return { token, expiresAt };
}

export const betterAuthInvitationPlugin: BetterAuthPlugin = {
  id: "oopsnote-invitations",
  version: "1.0.0",
  endpoints: {
    redeemInvitation: createAuthEndpoint("/invite/redeem", {
      method: "POST",
      body: invitationBody,
    }, async (ctx) => {
      const { token, password } = ctx.body;
      return runWithTransaction(ctx.context.adapter, async () => {
        const verification = await ctx.context.internalAdapter.consumeVerificationValue(invitationIdentifier(token));
        if (!verification) throw ctx.error("BAD_REQUEST", { message: "邀请链接无效或已过期" });
        let invitation: InvitationPayload;
        try {
          invitation = JSON.parse(verification.value) as InvitationPayload;
        } catch {
          throw ctx.error("BAD_REQUEST", { message: "邀请数据无效" });
        }
        if (!invitation.email || !invitation.name || !["admin", "user"].includes(invitation.role)) {
          throw ctx.error("BAD_REQUEST", { message: "邀请数据无效" });
        }
        if (await ctx.context.internalAdapter.findUserByEmail(invitation.email)) {
          throw ctx.error("BAD_REQUEST", { message: "该邮箱已经注册" });
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
        return ctx.json({ user });
      });
    }),
  },
};
