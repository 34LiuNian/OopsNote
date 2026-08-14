# Local authentication mode

Local mode is a loopback-only development convenience. The frontend skips the
login page and uses a fixed local administrator identity; the backend accepts
requests without a bearer token. It never creates a Better Auth user and must
not be used beyond loopback bindings.

Set both sides explicitly:

```dotenv
# frontend/.env.local
NEXT_PUBLIC_AUTH_MODE=local

# backend environment
OOPSNOTE_AUTH_MODE=local
```

For the Docker stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build frontend backend latex-renderer
```

Production and normal development default to Better Auth
(`NEXT_PUBLIC_AUTH_MODE=better-auth` / `OOPSNOTE_AUTH_MODE=better-auth`). The
first administrator is created through the one-time bootstrap flow (see
`deploy/README.md` and `deploy/oopsnote/secrets/README.md`). Return to Better
Auth by removing the two local-mode settings (or setting both values to
`better-auth`).
