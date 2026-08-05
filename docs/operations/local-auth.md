# Local authentication mode

Local mode is available for loopback development when Pocket ID is unavailable.
Set both sides explicitly:

```dotenv
# frontend/.env.local
NEXT_PUBLIC_AUTH_MODE=local

# backend environment
OOPSNOTE_AUTH_MODE=local
```

For the Docker stack, use the checked-in override so Pocket ID is not started:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build frontend backend latex-renderer
```

The frontend skips the OIDC redirect and uses a local administrator identity.
The backend accepts requests without a bearer token, including administrator
settings routes. This mode does not create an OIDC user or token and must only
be used behind a loopback-only frontend/backend binding. Keep the production
Compose stack on its default OIDC configuration.

To return to Pocket ID, remove the two local-mode settings (or set both values
to `oidc`) and provide the normal OIDC configuration.
