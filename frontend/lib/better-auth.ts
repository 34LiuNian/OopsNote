import Database from "better-sqlite3";
import { betterAuth } from "better-auth";
import { admin } from "better-auth/plugins";
import { nextCookies } from "better-auth/next-js";
import { ensureBetterAuthSchema } from "./better-auth-schema";
import fs from "node:fs";
import path from "node:path";

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

function authDatabasePath(): string {
  const databasePath = path.resolve(
    process.env.OOPSNOTE_AUTH_DB_PATH || path.join(process.cwd(), "data", "auth.sqlite"),
  );
  fs.mkdirSync(path.dirname(databasePath), { recursive: true });
  return databasePath;
}

const authDb = new Database(authDatabasePath());
authDb.pragma("journal_mode = WAL");
authDb.pragma("foreign_keys = ON");
authDb.pragma("busy_timeout = 5000");
ensureBetterAuthSchema(authDb);

const baseURL = (
  process.env.BETTER_AUTH_URL ||
  process.env.NEXT_PUBLIC_BETTER_AUTH_URL ||
  "http://localhost:3000"
).replace(/\/$/, "");

export const auth = betterAuth({
  appName: "OopsNote",
  baseURL,
  basePath: "/api/auth",
  secret: requiredSecret("BETTER_AUTH_SECRET", "OOPSNOTE_BETTER_AUTH_SECRET_FILE"),
  database: authDb,
  emailAndPassword: {
    enabled: true,
    disableSignUp: true,
    minPasswordLength: 12,
  },
  trustedOrigins: [baseURL],
  plugins: [
    admin({
      defaultRole: "user",
      adminRoles: ["admin"],
      bannedUserMessage: "此账号已被管理员禁用",
    }),
    nextCookies(),
  ],
});
