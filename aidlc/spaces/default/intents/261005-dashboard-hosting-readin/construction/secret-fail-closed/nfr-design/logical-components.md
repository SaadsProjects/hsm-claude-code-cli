# Logical Components — U1 secret-fail-closed

## Sources

- `security-design.md` (D1–D5); `inception/domain-design/components.md` (TokenAuth, MockBackend, PublishHook, McpTools, LocalSecretTooling, BurnedSecretCheck)
- `inception/contract-design/contract-summary.md` C1, C2

| Logical component | Where | Failure domain | Blast radius if it fails | Isolation |
|-------------------|-------|----------------|--------------------------|-----------|
| Secret gate (`require_secret`, `SecretMissingError`, burned-value hash) | `mock_hsm/auth.py` | Each process separately | That process can't mint or verify tokens; it fails closed | Re-read per call; no shared state between processes |
| Local loader (`load_local_secret`) | `mock_hsm/auth.py` | Local developer processes | Local tools refuse until `.env.local` exists | Never overrides a set value; never used when hosted |
| Backend refusal handling | `mock_hsm/server.py` (`__main__`, `_dispatch`) | Backend process | Startup refusal, or a 503 per affected request; the backend keeps serving | Caught ahead of the generic 500 handler |
| Hook gate | `.claude/hooks/require_no_violations.py` | One publish attempt | That publish is denied | Explicit deny; the broad catch stays as a backstop |
| Tool error | `mcp_server/hsm_tools.py` | One tool call | That call errors | Per call |
| Dev-secret and start scripts | `scripts/dev-secret.sh`, `scripts/start_mock_server.sh` | Developer machine | No local backend until fixed | Owner-only file; refuses to overwrite |
| Burned-literal scan | `scripts/check_burned_secret.py` and gitleaks in CI | Pull request | The merge is blocked | Required CI check |

**Shared resources:** the `HSM_SIGNING_SECRET` variable, copied into each child process, and the `.env.local` file. No other state is shared.

## Assumptions & Open Questions

None.
