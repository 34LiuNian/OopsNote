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

// 连接单例挂到 Symbol.for 注册表：Turbopack dev 的 RSC 与 SSR 是两个
// 模块图（各自的 globalThis 不同源，HMR 也会换掉整个 global），普通
// globalThis 单例无法跨图共享，会产生第二条连接。两条连接对同一
// auth.sqlite 各自开事务时锁升级互相等待，造成 register/sign-in 永久
// 挂死。Symbol.for 注册表与 better-auth 自身的跨 realm global（见
// @better-auth/core 的 __getBetterAuthGlobal）同属进程级，两个模块图
// 取到同一对象 → 全进程只有一条连接，锁域唯一，死锁无从形成。
const authDatabaseSingleton = Symbol.for("oopsnote:auth-database") as symbol;
const globalScope = globalThis as unknown as Record<symbol, { db?: Database.Database } | undefined>;
const singletonHolder = globalScope[authDatabaseSingleton] ?? (globalScope[authDatabaseSingleton] = {});
export const betterAuthDatabase =
  singletonHolder.db ?? (singletonHolder.db = new Database(authDatabasePath()));
// journal_mode 切换需要独占锁且不等 busy_timeout（实测并发设置方收到
// SQLITE_BUSY）。Next.js 的 RSC/SSR 双 runtime 会以独立模块图同时评估
// 本模块，两个连接并发对同一个尚未处于 WAL 的库执行模式切换；切换完成
// 后此调用幂等无害，因此捕获 BUSY 后短暂退避重试即可。读取当前模式可
// 以确认胜者已把库切到 WAL，稳态路径不重试。
for (let attempt = 0; ; attempt += 1) {
  try {
    const mode = betterAuthDatabase.pragma("journal_mode = WAL", { simple: true });
    if (mode !== "wal") {
      throw new Error(`Cannot enable WAL journal mode on auth database (got: ${mode})`);
    }
    break;
  } catch (error) {
    const isBusy =
      typeof error === "object" && error !== null && "code" in error && error.code === "SQLITE_BUSY";
    if (!isBusy || attempt >= 20) {
      throw error;
    }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, Math.min(50 * (attempt + 1), 500));
  }
}
betterAuthDatabase.pragma("foreign_keys = ON");
betterAuthDatabase.pragma("busy_timeout = 5000");

// 防 dev 期多模块图/多进程残留连接的锁升级死锁：kysely 用裸 BEGIN（DEFERRED），
// 两个连接各自 DEFERRED 事务在首条写语句上互相等待锁升级，busy handler 打破
// 不了这个环。改写为 BEGIN IMMEDIATE —— 事务一开始就取写锁，后来者按
// busy_timeout 排队，锁获取全序化，死锁环无从形成。对单连接（生产）无行为
// 差异，仅锁获取时机提前。
const prepareDirect = betterAuthDatabase.prepare.bind(betterAuthDatabase);
betterAuthDatabase.prepare = ((sql: string) =>
  sql.trim().toLowerCase() === "begin"
    ? prepareDirect("begin immediate")
    : prepareDirect(sql)) as typeof betterAuthDatabase.prepare;

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
