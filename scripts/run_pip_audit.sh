#!/bin/sh
# Runs pip-audit over both lockfiles and writes its JSON report to $1.
# pip-audit exits 1 when it finds vulnerabilities; that is expected here,
# because scripts/filter_audit.py decides pass or fail by severity. Any other
# non-zero exit is a tool failure and fails the job.
set -u
out="${1:-audit.json}"
bin="${PIP_AUDIT_BIN:-pip-audit}"

"$bin" -r requirements.txt -r requirements-dev.txt --require-hashes --format json --output "$out"
status=$?
case "$status" in
  0) echo "pip-audit: no known vulnerabilities" ;;
  1) echo "pip-audit: vulnerabilities found; filter_audit.py decides by severity" ;;
  *) echo "pip-audit: tool error (exit code $status)"; exit "$status" ;;
esac
exit 0
