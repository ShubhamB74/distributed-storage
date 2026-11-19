#!/usr/bin/env bash
# Create .env from .env.example with a freshly generated database password.
# Refuses to overwrite an existing .env.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -e .env ]]; then
  echo ".env already exists; refusing to overwrite it." >&2
  exit 1
fi

password="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
sed "s|^DISTRIBUTED_STORAGE_DB_PASSWORD=.*|DISTRIBUTED_STORAGE_DB_PASSWORD=${password}|" .env.example > .env
chmod 600 .env
echo "Created .env (mode 600) with a generated database password."
