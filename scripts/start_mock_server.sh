#!/usr/bin/env bash
# Starts the mock HSM backend in the foreground on 127.0.0.1:8770
# (matches HSM_BASE_URL in .mcp.json). Run this in its own terminal before
# starting `claude` in this project directory.
cd "$(dirname "$0")/.."
python3 -m mock_hsm.server
