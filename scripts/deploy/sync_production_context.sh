#!/usr/bin/env sh
# Synchronize only build inputs to the production Compose context.
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
target_root=${OOPSNOTE_PRODUCTION_CONTEXT:-/opt/oopsnote}

if [ ! -f "$target_root/docker-compose.yml" ]; then
    echo "production Compose context not found: $target_root" >&2
    exit 1
fi

mkdir -p "$target_root/oopsnote" "$target_root/frontend"
cp -a "$project_root/oopsnote/." "$target_root/oopsnote/"
cp -a "$project_root/skills/." "$target_root/skills/"
cp -a "$project_root/pyproject.toml" "$target_root/pyproject.toml"
cp -a "$project_root/deploy/backend/Dockerfile" "$target_root/deploy/backend/Dockerfile"
cp -a "$project_root/deploy/backend/entrypoint.sh" "$target_root/deploy/backend/entrypoint.sh"

for entry in app components config features hooks lib public scripts tests types; do
    cp -a "$project_root/frontend/$entry" "$target_root/frontend/"
done
for entry in \
    .dockerignore .env.example .gitignore .npmrc Dockerfile eslint.config.mjs \
    next-env.d.ts next.config.mjs package-lock.json package.json \
    playwright.config.ts playwright.credentialed.config.ts theme.ts tsconfig.json; do
    cp -a "$project_root/frontend/$entry" "$target_root/frontend/$entry"
done

echo "production build context synchronized: $target_root"
