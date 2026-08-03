#!/bin/sh
set -eu

source_key=${OOPSNOTE_SECRET_STORE_KEY_FILE:-/run/secrets/oopsnote_secret_store_key}
runtime_dir=/run/oopsnote
runtime_key=${runtime_dir}/secret_store_key

install -d -o oopsnote -g oopsnote -m 0700 "${runtime_dir}"
install -o oopsnote -g oopsnote -m 0400 "${source_key}" "${runtime_key}"
export OOPSNOTE_SECRET_STORE_KEY_FILE=${runtime_key}

exec gosu oopsnote "$@"
