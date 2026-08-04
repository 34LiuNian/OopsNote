# Public OIDC Deployment Handoff

This document records the live public deployment as of 2026-08-03. It contains no passwords, private keys, or runtime secrets.

## Public endpoints

- OopsNote: `https://oopsnote.alan-ztr.eu.org`
- Pocket ID issuer: `https://auth.alan-ztr.eu.org`
- Pocket ID OIDC client ID: `abd3d0b3-46f3-4aaa-994c-1c9258c74c1e`
- Production callback: `https://oopsnote.alan-ztr.eu.org/auth/callback`
- Production logout callback: `https://oopsnote.alan-ztr.eu.org/`

Pocket ID is a public PKCE client. It has no client secret. Registration should remain closed while OopsNote remains a single-admin deployment.

## Running architecture

```text
Public Internet
  -> oopsnote.alan-ztr.eu.org (DNS-only) -> 1Panel Caddy (host network)
     -> 127.0.0.1:13000 -> frontend container
     -> batch source PUT only -> 127.0.0.1:18000 -> backend container
  -> Cloudflare (Full strict) -> auth.alan-ztr.eu.org -> Caddy -> 127.0.0.1:14110 -> Pocket ID container

frontend container -> backend container -> latex-renderer internal network
backend container  -> Pocket ID JWKS over the Docker app network
```

`docker-compose.yml` is the source of application orchestration. The old nginx `gateway` service is intentionally removed. The frontend and Pocket ID ports are loopback-only.

The 1Panel Caddy configuration is mounted at:

```text
/opt/1panel/apps/caddy/caddy/data/conf/Caddyfile
```

The desired version is tracked in `deploy/caddy/Caddyfile`. Reload Caddy through its 1Panel container after updating it. Do not publish backend, Pocket ID, or frontend ports directly on all interfaces.

## Runtime-only state

Never add these to Git or overwrite them during a server checkout:

- `/opt/oopsnote/deploy/pocket-id/pocket-id.env`
- `/opt/oopsnote/deploy/pocket-id/secrets/encryption_key`
- Docker volumes `oopsnote-data` and `pocket-id-data`
- `/opt/oopsnote/deploy/pi/` and `/opt/oopsnote/deploy/pi-rust/` local runtime/auth state

Pocket ID needs `ENCRYPTION_KEY_FILE=/run/secrets/pocket_id_encryption_key`. The current Compose secret is backed by the server-only file above. It must remain readable by the Pocket ID container user.

The server has 4 GiB RAM and a persistent 2 GiB `/swapfile`, added because production Next.js builds exhausted RAM without swap. Preserve the `/etc/fstab` swap entry.

## OIDC implementation

- Frontend implementation: `frontend/lib/auth.ts`.
- The browser performs Authorization Code + PKCE, stores the short-lived access token in `sessionStorage`, and calls Pocket ID `userinfo` to store display data for the header account menu.
- Backend implementation: `oopsnote/api/auth.py` and the middleware in `oopsnote/api/main.py`.
- The backend validates issuer and audience from the public issuer, but downloads JWKS internally from `http://pocket-id:1411/.well-known/jwks.json` via `OOPSNOTE_AUTH_JWKS_URL`.

This split is deliberate: Python's JWKS client received Cloudflare `403` when it requested the public auth hostname. Do not remove `OOPSNOTE_AUTH_JWKS_URL` or replace it with the public hostname unless the Cloudflare behavior is independently verified.

`/health` remains public for container health checks. All other backend routes require a valid bearer token when OIDC is configured. A failed JWKS connection returns `503`; invalid or unknown-key tokens return `401`.

The current authorization boundary is a single authenticated-admin gate. OopsNote storage is not yet partitioned by OIDC `sub`. Do not enable self-registration or multiple independent users until Core/API storage ownership isolation is designed and implemented.

## Cloudflare and uploads

`oopsnote.alan-ztr.eu.org` is DNS-only so batch source uploads up to 500 MiB
can reach the Caddy origin without Cloudflare's proxied request-size limit.
Caddy must retain its valid public origin certificate. `auth.alan-ztr.eu.org`
remains Cloudflare-proxied with SSL/TLS set to `Full (strict)`; Rocket Loader
must remain disabled there because it injected inline scripts that Pocket ID CSP
correctly blocked, causing a blank setup page.

Next.js rejects proxied request bodies above its default 10 MiB limit. Caddy
therefore routes only `PUT /api/batch-sessions/<sha256>/source` directly to the
loopback-only backend port `18000`; it strips `/api` before proxying. The
backend remains responsible for bearer-token validation, streaming, hash
validation, and the 500 MiB limit. All other `/api` paths stay behind Next.

## Deployment commands

From `/opt/oopsnote` on the server:

```bash
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
docker compose ps
```

For an isolated rebuild, prefer one service at a time on this small server:

```bash
docker compose build frontend
docker compose up -d --no-deps frontend
```

Do not use a broad destructive Compose teardown. Existing volumes contain user data and Pocket ID state.

## Verification

Local checks used for this change:

```powershell
$env:PYTEST_ADDOPTS='--basetemp=E:/works/2026/OopsNote/.pytest-tmp-auth'
.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q
Set-Location frontend
npm run lint
```

The server frontend production build completed successfully after the swap change. Public checks confirmed the homepage returns `200`, invalid bearer tokens return `401`, and the browser-facing userinfo endpoint allows the OopsNote origin.

Credentialed browser login must be checked manually after changes to the OIDC flow.

## Remote development

The current `/opt/oopsnote` directory was manually synchronized during deployment and previously lagged the local workspace. Before turning it into a development checkout, reconcile it deliberately with Git while preserving the runtime-only files listed above.

For a smooth remote workflow, keep production and development directories separate:

- `/opt/oopsnote`: production Compose stack
- `/opt/oopsnote-dev`: a normal `develop` branch checkout with source bind mounts and `next dev`/backend reload
- a separate `dev-oopsnote` hostname and separate Pocket ID PKCE client

Do not point the production public hostname at a development server unless that interruption and exposure are intentional.
