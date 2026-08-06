# ADR-0001: Better Auth and multi-user foundation

Status: accepted for implementation  
Date: 2026-08-07

## Decision

- Pin `better-auth` to `1.6.26` and `better-sqlite3` to `13.0.3`.
- Keep Better Auth and `auth.sqlite` exclusively inside the Next.js process.
- Use the Better Auth admin plugin with only `admin` and `user` product roles.
- Keep application ownership, workspace mapping, runs, and quota accounting in the Python-owned `app.sqlite`.
- Carry a registry-derived `WorkspaceId` through REST, managed lifecycle, and MCP boundaries. Never derive a workspace from a browser-supplied path or resource owner field.
- Treat public sign-up as closed. The invite redemption endpoint remains disabled until its transaction test proves that invite validation, account creation, and token consumption have one atomic outcome.

## Version evidence

The npm registry reported `better-auth@1.6.26` as the stable release on 2026-08-07. Its peer contract supports Next.js 16, React 19, and `better-sqlite3 ^12`. The selected `better-sqlite3@13.0.3` requires Node 22 or newer; both development and the production Dockerfile use Node 24.

The pinned package exports the official Next.js handler, admin plugin, client admin plugin, database migration API, and database hooks. The admin contract includes user creation/listing, role assignment, ban/unban, session listing, and session revocation.

## Invitation transaction gate

Better Auth database hooks are useful policy boundaries, but the public API does not prove that an OopsNote custom invitation row and Better Auth account writes share one externally controlled transaction. OopsNote will therefore not implement invitation redemption as a hook plus a second write.

Phase 4 must choose and contract-test one Node-owned atomic mechanism against the pinned version:

1. a custom Better Auth endpoint/plugin whose adapter transaction owns invitation validation, account creation, and token consumption; or
2. a Better Auth native one-time record that is consumed in the same account-creation transaction.

The test must inject a failure after account preparation and prove that neither an account nor a consumed invitation remains. Until that test passes, only an explicit bootstrap command may create the first administrator.

## Migration ownership

- Better Auth schema SQL is generated from the pinned dependency's official migration API, committed as a versioned artifact, and applied only by the Next.js process at startup.
- OopsNote control-plane schema changes use ordered SQL migrations packaged with Python.
- Neither process reads or migrates the other process's database.

## Consequences

This adds two SQLite files but not two sources of truth: identity state belongs to Better Auth; application ownership and usage state belong to the backend. The physical workspace directory is derived from the immutable backend mapping. A missing directory can be recreated from that mapping, while a directory can never establish identity on its own.

Passkeys remain deferred until invitation, password login, session revocation, and account recovery are working. This keeps passkey-specific failure states out of the initial authentication cutover.
