import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { ensureBetterAuthSchema } from "./better-auth-schema";

function authDatabasePath(): string {
  const databasePath = path.resolve(
    process.env.OOPSNOTE_AUTH_DB_PATH || path.join(process.cwd(), "data", "auth.sqlite"),
  );
  fs.mkdirSync(path.dirname(databasePath), { recursive: true });
  return databasePath;
}

export const betterAuthDatabase = new Database(authDatabasePath());
betterAuthDatabase.pragma("journal_mode = WAL");
betterAuthDatabase.pragma("foreign_keys = ON");
betterAuthDatabase.pragma("busy_timeout = 5000");
ensureBetterAuthSchema(betterAuthDatabase);

export type BetterAuthIdentityStats = {
  totalUsers: number;
  adminUsers: number;
  activeAdminUsers: number;
};

/** Server-only bootstrap/guard queries; Better Auth remains the identity source of truth. */
export function betterAuthIdentityStats(): BetterAuthIdentityStats {
  const row = betterAuthDatabase
    .prepare(
      `select
         count(*) as totalUsers,
         sum(case when role = 'admin' or role like '%admin%' then 1 else 0 end) as adminUsers,
         sum(case when (role = 'admin' or role like '%admin%') and coalesce(banned, 0) = 0 then 1 else 0 end) as activeAdminUsers
       from "user"`,
    )
    .get() as { totalUsers: number; adminUsers: number | null; activeAdminUsers: number | null };
  return {
    totalUsers: Number(row.totalUsers || 0),
    adminUsers: Number(row.adminUsers || 0),
    activeAdminUsers: Number(row.activeAdminUsers || 0),
  };
}
