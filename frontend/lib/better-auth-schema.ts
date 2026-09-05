import type Database from "better-sqlite3";

// Generated with better-auth@1.6.26's getMigrations().compileMigrations().
// Keep this versioned artifact in lockstep with the pinned Better Auth package.
const migrations = [
  {
    version: 1,
    name: "0001_better_auth_core",
    sql: `
create table "user" ("id" text not null primary key, "name" text not null, "email" text not null unique, "emailVerified" integer not null, "image" text, "createdAt" date not null, "updatedAt" date not null, "role" text, "banned" integer, "banReason" text, "banExpires" date);
create table "session" ("id" text not null primary key, "expiresAt" date not null, "token" text not null unique, "createdAt" date not null, "updatedAt" date not null, "ipAddress" text, "userAgent" text, "userId" text not null references "user" ("id") on delete cascade, "impersonatedBy" text);
create table "account" ("id" text not null primary key, "accountId" text not null, "providerId" text not null, "userId" text not null references "user" ("id") on delete cascade, "accessToken" text, "refreshToken" text, "idToken" text, "accessTokenExpiresAt" date, "refreshTokenExpiresAt" date, "scope" text, "password" text, "createdAt" date not null, "updatedAt" date not null);
create table "verification" ("id" text not null primary key, "identifier" text not null, "value" text not null, "expiresAt" date not null, "createdAt" date not null, "updatedAt" date not null);
create index "session_userId_idx" on "session" ("userId");
create index "account_userId_idx" on "account" ("userId");
create index "verification_identifier_idx" on "verification" ("identifier");
`.trim(),
  },
  {
    version: 2,
    name: "0002_oopsnote_invitations_and_audit",
    sql: `
create table "oopsnote_invitation" (
  "id" text not null primary key,
  "tokenHash" text not null unique,
  "email" text not null,
  "name" text not null,
  "role" text not null check ("role" in ('admin', 'user')),
  "initialDailySuccessLimit" integer not null default 20 check ("initialDailySuccessLimit" >= 0),
  "createdByUserId" text not null,
  "createdAt" text not null,
  "expiresAt" text not null,
  "consumedAt" text,
  "consumedUserId" text,
  "workspaceProvisionedAt" text,
  "revokedAt" text,
  "revokedByUserId" text
);
create index "oopsnote_invitation_email_idx" on "oopsnote_invitation" ("email");
create index "oopsnote_invitation_active_idx" on "oopsnote_invitation" ("consumedAt", "revokedAt", "expiresAt");
create table "oopsnote_auth_audit" (
  "id" text not null primary key,
  "actorUserId" text not null,
  "action" text not null,
  "targetUserId" text,
  "invitationId" text,
  "metadataJson" text not null default '{}',
  "createdAt" text not null
);
create index "oopsnote_auth_audit_created_idx" on "oopsnote_auth_audit" ("createdAt");
create index "oopsnote_auth_audit_actor_idx" on "oopsnote_auth_audit" ("actorUserId", "createdAt");
`.trim(),
  },
  {
    version: 3,
    name: "0003_auth_invariants",
    sql: `
create table "oopsnote_bootstrap_state" (
  "id" integer not null primary key check ("id" = 1),
  "completedAt" text
);
insert into "oopsnote_bootstrap_state" ("id", "completedAt") values (1, null);
create trigger "oopsnote_keep_active_admin_on_update"
before update of "role", "banned" on "user"
when
  (old."role" = 'admin' or old."role" like '%admin%')
  and coalesce(old."banned", 0) = 0
  and not ((new."role" = 'admin' or new."role" like '%admin%') and coalesce(new."banned", 0) = 0)
  and not exists (
    select 1 from "user"
    where "id" <> old."id"
      and ("role" = 'admin' or "role" like '%admin%')
      and coalesce("banned", 0) = 0
  )
begin
  select raise(abort, 'OOPSNOTE_LAST_ACTIVE_ADMIN');
end;
create trigger "oopsnote_keep_active_admin_on_delete"
before delete on "user"
when
  (old."role" = 'admin' or old."role" like '%admin%')
  and coalesce(old."banned", 0) = 0
  and not exists (
    select 1 from "user"
    where "id" <> old."id"
      and ("role" = 'admin' or "role" like '%admin%')
      and coalesce("banned", 0) = 0
  )
begin
  select raise(abort, 'OOPSNOTE_LAST_ACTIVE_ADMIN');
end;
`.trim(),
  },
  {
    version: 4,
    name: "0004_bootstrap_claim_lease",
    sql: `
alter table "oopsnote_bootstrap_state" add column "claimToken" text;
alter table "oopsnote_bootstrap_state" add column "claimedAt" text;
`.trim(),
  },
  {
    version: 5,
    name: "0005_username_registration_policy",
    sql: `
alter table "user" add column "username" text;
alter table "user" add column "displayUsername" text;
update "user"
set "username" = case
  when lower("email") = 'alan@oopsnote.local' then 'alan'
  else 'user_' || substr(replace("id", '-', ''), 1, 12)
end;
update "user" set "displayUsername" = "username";
create unique index "user_username_uidx" on "user" ("username");

drop index "oopsnote_invitation_email_idx";
drop index "oopsnote_invitation_active_idx";
alter table "oopsnote_invitation" rename to "oopsnote_invitation_legacy";
create table "oopsnote_invitation" (
  "id" text not null primary key,
  "tokenHash" text not null unique,
  "maxUses" integer not null check ("maxUses" between 1 and 100),
  "useCount" integer not null default 0 check ("useCount" between 0 and "maxUses"),
  "initialDailySuccessLimit" integer not null default 20 check ("initialDailySuccessLimit" between 0 and 1000000),
  "createdByUserId" text not null,
  "createdAt" text not null,
  "expiresAt" text not null,
  "revokedAt" text,
  "revokedByUserId" text
);
insert into "oopsnote_invitation" (
  "id", "tokenHash", "maxUses", "useCount", "initialDailySuccessLimit",
  "createdByUserId", "createdAt", "expiresAt", "revokedAt", "revokedByUserId"
)
select
  "id", "tokenHash", 1, case when "consumedAt" is null then 0 else 1 end,
  "initialDailySuccessLimit", "createdByUserId", "createdAt", "expiresAt",
  "revokedAt", "revokedByUserId"
from "oopsnote_invitation_legacy";
create index "oopsnote_invitation_active_idx" on "oopsnote_invitation" ("revokedAt", "expiresAt", "useCount", "maxUses");

create table "oopsnote_invitation_redemption" (
  "id" text not null primary key,
  "invitationId" text not null references "oopsnote_invitation" ("id") on delete cascade,
  "userId" text not null unique references "user" ("id") on delete cascade,
  "createdAt" text not null
);
insert into "oopsnote_invitation_redemption" ("id", "invitationId", "userId", "createdAt")
select 'legacy-' || "id", "id", "consumedUserId", "consumedAt"
from "oopsnote_invitation_legacy"
where "consumedUserId" is not null and "consumedAt" is not null;
create index "oopsnote_invitation_redemption_invite_idx" on "oopsnote_invitation_redemption" ("invitationId", "createdAt");

create table "oopsnote_user_provisioning" (
  "userId" text not null primary key references "user" ("id") on delete cascade,
  "dailySuccessLimit" integer not null check ("dailySuccessLimit" between 0 and 1000000),
  "source" text not null check ("source" in ('invitation', 'open', 'admin')),
  "createdAt" text not null,
  "provisionedAt" text
);
insert into "oopsnote_user_provisioning" ("userId", "dailySuccessLimit", "source", "createdAt", "provisionedAt")
select "consumedUserId", "initialDailySuccessLimit", 'invitation', "consumedAt", "workspaceProvisionedAt"
from "oopsnote_invitation_legacy"
where "consumedUserId" is not null and "consumedAt" is not null;

drop table "oopsnote_invitation_legacy";

create table "oopsnote_registration_policy" (
  "id" integer not null primary key check ("id" = 1),
  "mode" text not null check ("mode" in ('closed', 'invite', 'open')),
  "openDailySuccessLimit" integer not null check ("openDailySuccessLimit" between 0 and 1000000),
  "updatedAt" text not null,
  "updatedByUserId" text
);
insert into "oopsnote_registration_policy" (
  "id", "mode", "openDailySuccessLimit", "updatedAt", "updatedByUserId"
) values (1, 'invite', 5, datetime('now'), null);
`.trim(),
  },
  {
    version: 6,
    name: "0006_normalize_existing_usernames",
    sql: `
update "user" set "username" = lower("username") where "username" is not null;
update "user"
set "username" = 'alan', "displayUsername" = 'Alan'
where "id" = (
  select "id" from "user"
  where ("role" = 'admin' or "role" like '%admin%') and coalesce("banned", 0) = 0
  order by "createdAt" asc limit 1
)
and not exists (select 1 from "user" where "username" = 'alan');
`.trim(),
  },
  {
    version: 7,
    name: "0007_queue_existing_user_provisioning",
    sql: `
insert into "oopsnote_user_provisioning" (
  "userId", "dailySuccessLimit", "source", "createdAt", "provisionedAt"
)
select "id", 20, 'admin', "createdAt", null
from "user"
where not exists (
  select 1 from "oopsnote_user_provisioning" as provisioning
  where provisioning."userId" = "user"."id"
);
`.trim(),
  },
  {
    version: 8,
    name: "0008_mark_legacy_provisioning",
    sql: `
alter table "oopsnote_user_provisioning" add column "preserveExistingQuota" integer not null default 0 check ("preserveExistingQuota" in (0, 1));
update "oopsnote_user_provisioning"
set "preserveExistingQuota" = 1
where "source" = 'admin'
  and "provisionedAt" is null
  and "createdAt" <= (select "appliedAt" from "_oopsnote_auth_schema_migrations" where "version" = 7);
`.trim(),
  },
] as const;

/** 迁移清单：供测试与诊断读取；运行时只经 ensureBetterAuthSchema 应用。 */
export const authSchemaMigrations = migrations;

const expectedMigrations: Record<number, string> = Object.fromEntries(
  migrations.map((migration) => [migration.version, migration.name]),
);
const MIGRATION_BUSY_TIMEOUT_MS = 30_000;

function readAppliedMigrations(database: Database.Database): { version: number; name: string }[] {
  return database
    .prepare('select "version", "name" from "_oopsnote_auth_schema_migrations"')
    .all() as { version: number; name: string }[];
}

export function ensureBetterAuthSchema(database: Database.Database): void {
  // 稳态快速路径：迁移表已存在且全部版本按名匹配时只做读校验，不抢写锁。
  // 本函数在模块评估时执行，Next.js dev/构建的并发 worker 会对同一库同时
  // 触发；无条件 BEGIN IMMEDIATE 会让后到方在 busy_timeout 内拿不到写锁
  // 而抛 SQLITE_BUSY（"database is locked"）。已迁移完成的启动不应碰写锁。
  const migrationTable = database
    .prepare(
      "select 1 from sqlite_master where type = 'table' and name = '_oopsnote_auth_schema_migrations'",
    )
    .get();
  if (migrationTable) {
    const appliedRows = readAppliedMigrations(database);
    if (
      appliedRows.length === Object.keys(expectedMigrations).length &&
      appliedRows.every((row) => expectedMigrations[Number(row.version)] === row.name)
    ) {
      return;
    }
  }
  const applyMigrations = database.transaction(() => {
    database.exec(`
      create table if not exists "_oopsnote_auth_schema_migrations" (
        "version" integer not null primary key,
        "name" text not null unique,
        "appliedAt" text not null
      );
    `);
    const appliedRows = readAppliedMigrations(database);
    for (const row of appliedRows) {
      if (expectedMigrations[Number(row.version)] !== row.name) {
        throw new Error(`Unknown or mismatched Better Auth schema migration: ${row.version}`);
      }
    }
    const applied = new Set<number>(appliedRows.map((row) => Number(row.version)));
    for (const migration of migrations) {
      if (applied.has(migration.version)) continue;
      database.exec(migration.sql);
      database
        .prepare(
          'insert into "_oopsnote_auth_schema_migrations" ("version", "name", "appliedAt") values (?, ?, ?)',
        )
        .run(migration.version, migration.name, new Date().toISOString());
    }
  });
  // 冷启动/升级需要写锁：临时加长 busy_timeout，覆盖并发 worker 持锁迁移
  // 的整个窗口。BEGIN IMMEDIATE 保证等待方拿到锁后重读已应用版本，避免
  // check-then-ALTER 竞态产生 "duplicate column name"（见 CI 前端镜像构建）。
  const previousBusyTimeout = database.pragma("busy_timeout", { simple: true }) as number;
  database.pragma(`busy_timeout = ${MIGRATION_BUSY_TIMEOUT_MS}`);
  try {
    applyMigrations.immediate();
  } finally {
    database.pragma(`busy_timeout = ${previousBusyTimeout}`);
  }
}
