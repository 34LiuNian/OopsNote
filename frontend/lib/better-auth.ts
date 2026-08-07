import { betterAuth } from "better-auth";
import { admin, username } from "better-auth/plugins";
import { nextCookies } from "better-auth/next-js";
import { SqliteDialect } from "kysely";
import { betterAuthInvitationPlugin } from "./better-auth-invitations";
import { betterAuthDatabase } from "./better-auth-database";
import { betterAuthAdminGatePlugin } from "./better-auth-admin-gate";
import { normalizeUsername } from "./better-auth-registration";
export { betterAuthIdentityStats } from "./better-auth-database";
import fs from "node:fs";

function requiredSecret(name: string, fileName: string): string {
  const configuredPath = process.env[fileName]?.trim();
  if (configuredPath) {
    const value = fs.readFileSync(configuredPath, "utf8").trim();
    if (value) return value;
    throw new Error(`${fileName} points to an empty secret file`);
  }
  const value = process.env[name]?.trim();
  if (value) return value;
  throw new Error(`${fileName} or ${name} must be configured`);
}

const baseURL = (
  process.env.BETTER_AUTH_URL ||
  process.env.NEXT_PUBLIC_BETTER_AUTH_URL ||
  "http://localhost:3000"
).replace(/\/$/, "");
const trustedOrigins = new Set([baseURL]);
if (process.env.NODE_ENV === "development") {
  trustedOrigins.add("http://localhost:3000");
  trustedOrigins.add("http://127.0.0.1:3000");
}

export const auth = betterAuth({
  appName: "OopsNote",
  baseURL,
  basePath: "/api/auth",
  secret: requiredSecret("BETTER_AUTH_SECRET", "OOPSNOTE_BETTER_AUTH_SECRET_FILE"),
  database: {
    dialect: new SqliteDialect({ database: betterAuthDatabase }),
    type: "sqlite",
    transaction: true,
  },
  emailAndPassword: {
    enabled: true,
    disableSignUp: true,
    minPasswordLength: 12,
  },
  user: {
    changeEmail: {
      enabled: true,
      // Internal beta accounts are not email-verified yet; keep this update in Better Auth,
      // rather than allowing any application route to write identity rows directly.
      updateEmailWithoutVerification: true,
    },
  },
  trustedOrigins: [...trustedOrigins],
  plugins: [
    betterAuthAdminGatePlugin,
    admin({
      defaultRole: "user",
      adminRoles: ["admin"],
      bannedUserMessage: "此账号已被管理员禁用",
    }),
    username({
      minUsernameLength: 3,
      maxUsernameLength: 32,
      usernameValidator: (value) => {
        try {
          normalizeUsername(value);
          return true;
        } catch {
          return false;
        }
      },
    }),
    betterAuthInvitationPlugin,
    nextCookies(),
  ],
});
