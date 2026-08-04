#!/bin/sh
set -eu

source_key=${OOPSNOTE_SECRET_STORE_KEY_FILE:-/run/secrets/oopsnote_secret_store_key}
runtime_dir=/run/oopsnote
runtime_key=${runtime_dir}/secret_store_key
vault_path=${OOPSNOTE_SECRET_STORE_PATH:-/vault/credentials.json}
vault_dir=$(dirname "${vault_path}")

install -d -o oopsnote -g oopsnote -m 0700 "${runtime_dir}"
install -o oopsnote -g oopsnote -m 0400 "${source_key}" "${runtime_key}"
# A previous root-running image may have created this file on the persistent
# volume. Repair only the service-owned vault file before dropping privileges.
install -d -o oopsnote -g oopsnote -m 0700 "${vault_dir}"
if [ -f "${vault_path}" ]; then
  chown oopsnote:oopsnote "${vault_path}"
  chmod 0600 "${vault_path}"
fi
export OOPSNOTE_SECRET_STORE_KEY_FILE=${runtime_key}

exec gosu oopsnote "$@"
