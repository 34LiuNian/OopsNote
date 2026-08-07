# ADR-0001: Better Auth and multi-user foundation

Status: accepted for implementation  
Date: 2026-08-07

## Decision

- Pin `better-auth` to `1.6.26`, `better-sqlite3` to `13.0.3`, and `kysely` to `0.29.4`.
- Keep Better Auth and `auth.sqlite` exclusively inside the Next.js process.
- Use the Better Auth admin plugin with only `admin` and `user` product roles.
- Keep application ownership, workspace mapping, runs, and quota accounting in the Python-owned `app.sqlite`.
- Carry a registry-derived `WorkspaceId` through REST, managed lifecycle, and MCP boundaries. Never derive a workspace from a browser-supplied path or resource owner field.
- Treat public sign-up as closed. Beta members are created through the admin invitation flow or the explicitly labeled direct-admin flow.
- Enable Better Auth's Kysely SQLite transaction adapter. The custom invitation endpoint atomically claims a hashed OopsNote invitation row and creates the user plus credential account in that same transaction.

## Version evidence

The npm registry reported `better-auth@1.6.26` as the stable release on 2026-08-07. Its peer contract supports Next.js 16, React 19, and `better-sqlite3 ^12`. The selected `better-sqlite3@13.0.3` requires Node 22 or newer; both development and the production Dockerfile use Node 24.

The pinned packages export the official Next.js handler, admin plugin, client admin plugin, database migration API, and database hooks. The admin contract includes user creation/listing, role assignment, ban/unban, session listing, and session revocation. Kysely `transaction: true` is required because its default is sequential execution.

## Invitation transaction gate

Better Auth database hooks remain policy boundaries; invitation redemption is implemented as a custom Better Auth endpoint/plugin. The Node-owned `oopsnote_invitation` table stores only a SHA-256 token digest and explicit created, expiry, consumed, and revoked state. The endpoint conditionally claims one active row, validates it, and creates the user and credential account before the transaction commits. Sensitive account and invitation operations append structured records to `oopsnote_auth_audit`. Public sign-up remains disabled.

The contract test against the pinned version proves: first redemption succeeds, replay is rejected, duplicate-email redemption fails without consuming the invitation, deleting the existing account allows the failed invitation to be redeemed, and the replay of that redeemed invitation is rejected.

## Migration ownership

- Better Auth schema SQL is generated from the pinned dependency's official migration API, committed as a versioned artifact, and applied only by the Next.js process at startup.
- OopsNote control-plane schema changes use ordered SQL migrations packaged with Python.
- Neither process reads or migrates the other process's database.

## Consequences

This adds two SQLite files but not two sources of truth: identity state belongs to Better Auth; application ownership and usage state belong to the backend. The physical workspace directory is derived from the immutable backend mapping. A missing directory can be recreated from that mapping, while a directory can never establish identity on its own.

Passkeys remain deferred until invitation, password login, session revocation, and account recovery are working. This keeps passkey-specific failure states out of the initial authentication cutover.
