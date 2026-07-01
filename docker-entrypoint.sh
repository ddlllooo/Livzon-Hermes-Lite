#!/bin/sh
set -eu

mkdir -p "${HERMES_HOME:-/data/hermes}"

if [ ! -f "${HERMES_HOME:-/data/hermes}/config.yaml" ] && [ -f /app/config.yaml ]; then
  cp /app/config.yaml "${HERMES_HOME:-/data/hermes}/config.yaml"
fi

exec "$@"
