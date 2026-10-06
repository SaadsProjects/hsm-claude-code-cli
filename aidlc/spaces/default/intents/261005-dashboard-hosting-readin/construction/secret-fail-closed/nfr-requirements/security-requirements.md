# Security Requirements — U1 secret-fail-closed

## Sources

- `inception/requirements-analysis/requirements.md` NFR1, NFR3, NFR4, NFR7
- `construction/secret-fail-closed/functional-design/rules.md` (BR1.1–BR6.1) and `functional-spec.md` (W1–W9)
- `inception/contract-design/contract-summary.md` C1, C2
- `nfr-requirements-questions.md` Q1, Q2; `memory/project.md` (M1, F2, R-SEC-3); `memory/team.md` Deployment, Testing Posture

## Threat Model (STRIDE, scoped to U1)

| Asset or flow | Threat | Mitigation (requirement) |
|---------------|--------|--------------------------|
| Signing secret in source (today's burned literal) | Information disclosure; spoofing (anyone can mint tokens for any persona) | NFR1.1, NFR1.2, NFR1.6 |
| A process started without a secret | Spoofing or crash (a crashed hook fails open) | NFR1.3, NFR1.4, NFR1.5 |
| A weak or reused secret (short, or the old burned value) | Spoofing (guessable or known key) | NFR1.2, NFR1.7 |
| Secret value in error messages, logs or committed config | Information disclosure | NFR1.6, NFR1.8 |
| `.env.local` on disk | Information disclosure (other local users, accidental commit) | NFR1.8, NFR1.9 |

## Requirements

| ID | Requirement | Pass condition | Source |
|----|-------------|----------------|--------|
| NFR1.1 | No signing secret, burned or otherwise, exists in source code; `TEMPORARY_EXCLUSIONS` is empty | The burned-secret check passes with an empty exclusion list; gitleaks passes | NFR1, BR2.1, M1 |
| NFR1.2 | Every secret is at least 32 UTF-8 bytes; anything shorter is refused; exactly 32 is accepted | Unit tests at 31 and 32 bytes | NFR1, BR1.4 |
| NFR1.3 | No process has a fallback secret: tokens can't be minted or verified without one | A test with the variable unset shows mint and verify refusing | NFR1, BR1.6, R-SEC-3 |
| NFR1.4 | The publish hook denies `publish_schedule` explicitly when it has no valid secret | Hook test (written first): with no secret, the output is a deny naming `HSM_SIGNING_SECRET` | NFR1, BR4.1 |
| NFR1.5 | The separate-process backend and the start script refuse to start without a valid secret; a running backend answers 503 on a mid-run secret failure | Subprocess tests: non-zero exit and no listener; a handler test shows 503 for both verify and mint paths (functional-design review item R-04) | NFR1, BR3.3–BR3.5 |
| NFR1.6 | No error, log line or tool output ever contains the secret value | Tests capture the messages for each refusal path and assert the value is absent | NFR1, BR1.5 |
| NFR1.7 | The old burned value is refused even though it is long enough, by comparing its SHA-256 against a stored hash; the literal never reappears | A test feeds the burned value from the test's stand-in source and expects a refusal; the scan still passes | Q1 |
| NFR1.8 | The secret never appears in committed configuration (`.mcp.json`, settings examples, `.streamlit/config.toml`) | A test asserts `.mcp.json` holds no `HSM_SIGNING_SECRET` value; gitleaks passes | NFR1, BR4.2, F2 |
| NFR1.9 | `.env.local` is created owner-read/write only (mode 600) and is git-ignored by an explicit line outside the AI-DLC block, as are `.env`, `.env.*` and `.streamlit/secrets.toml` | A test checks the mode after the dev-secret script runs; `git check-ignore` succeeds for each path | Q2, BR5.1, F2 |
| NFR1.10 | The `.env.local` loader never overrides a variable already set, reads only `KEY=VALUE` lines (no shell expansion), and resolves the project root from its own file location | Loader unit tests: set variable kept; expansion text taken literally; works from another working directory | BR3.1; functional-design review item R-03 |
| NFR3.1 | All of U1 is test-first; tests ship with the code; the suite stays at or above `.test-floor` on 3.10 and 3.14, and coverage at or above `.coverage-floor` | CI on pull request 1: `tests (3.10)`, `tests (3.14)` and `coverage-gate` green | NFR3, team.md Testing Posture |
| NFR3.2 | Tests generate their own secret per run; none is committed | conftest test; gitleaks | NFR3, BR2.2 |
| NFR4.1 | Each refusal surface names the variable and the rule broken, so a developer can fix it without reading code | Message assertions in the refusal tests | NFR4, BR1.3–BR1.5 |
| NFR7.1 | U1 adds no dependency; `lock-check` and `audit` stay green | CI on pull request 1 | NFR7 |

## Assumptions & Open Questions

None.
