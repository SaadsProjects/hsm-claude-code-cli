#!/usr/bin/env bash
# Starts the mock HSM backend in the foreground on 127.0.0.1:8770 (matches
# HSM_BASE_URL in .mcp.json), or on another port with `--port N`. Run this in
# its own terminal before starting `claude` in this project directory.
#
# The backend needs HSM_SIGNING_SECRET. If it isn't exported, the backend
# reads it from .env.local (create that once with scripts/dev-secret.sh). With
# no usable secret it prints why and exits non-zero without listening. Python
# is the only reader of .env.local: this script never sources the file.
cd "$(dirname "$0")/.." || exit 1
exec python3 -m mock_hsm.server "$@"
