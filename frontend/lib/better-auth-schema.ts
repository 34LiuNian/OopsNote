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
] as const;

export function ensureBetterAuthSchema(database: Database.Database): void {
  database.exec(`
    create table if not exists "_oopsnote_auth_schema_migrations" (
      "version" integer not null primary key,
      "name" text not null unique,
      "appliedAt" text not null
    );
  `);
  const expected = new Map<number, string>(
    migrations.map((migration) => [migration.version, migration.name]),
  );
  const appliedRows = database
    .prepare('select "version", "name" from "_oopsnote_auth_schema_migrations"')
    .all() as { version: number; name: string }[];
  for (const row of appliedRows) {
    if (expected.get(Number(row.version)) !== row.name) {
      throw new Error(`Unknown or mismatched Better Auth schema migration: ${row.version}`);
    }
  }
  const applied = new Set<number>(appliedRows.map((row) => Number(row.version)));
  for (const migration of migrations) {
    if (applied.has(migration.version)) continue;
    const apply = database.transaction(() => {
      database.exec(migration.sql);
      database
        .prepare(
          'insert into "_oopsnote_auth_schema_migrations" ("version", "name", "appliedAt") values (?, ?, ?)',
        )
        .run(migration.version, migration.name, new Date().toISOString());
    });
    apply();
  }
}
