#!/usr/bin/env bash
# Writes a fresh local token-signing secret into .env.local (git-ignored):
#
#     scripts/dev-secret.sh             # create it once
#     scripts/dev-secret.sh --force     # replace an existing one
#     scripts/dev-secret.sh --file PATH # another file (the tests use this)
#
# The backend, the start script, the publish hook and the MCP server read
# HSM_SIGNING_SECRET from .env.local when it isn't exported. Other lines in
# the file are kept. The file is owner read/write only (mode 600), and the
# value is never printed.
set -euo pipefail

usage() {
  echo "usage: scripts/dev-secret.sh [--force] [--file PATH]" >&2
  exit 2
}

project_root="$(cd "$(dirname "$0")/.." && pwd)"
file="$project_root/.env.local"
force=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force) force=1 ;;
    --file)
      [ $# -ge 2 ] || usage
      file="$2"
      shift
      ;;
    *) usage ;;
  esac
  shift
done

key="HSM_SIGNING_SECRET"
if [ -f "$file" ] && grep -q "^$key=" "$file" && [ "$force" -ne 1 ]; then
  echo "$key is already set in $file; use --force to replace it." >&2
  exit 1
fi

umask 077
value="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
tmp="$(mktemp "$file.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
if [ -f "$file" ]; then
  grep -v "^$key=" "$file" > "$tmp" || true # no other lines is not an error
fi
printf '%s=%s\n' "$key" "$value" >> "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$file"
chmod 600 "$file"
trap - EXIT
echo "Wrote a new $key to $file (mode 600)."
