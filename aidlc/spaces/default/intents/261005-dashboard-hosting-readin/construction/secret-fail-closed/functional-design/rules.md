# Business Rules — U1 secret-fail-closed

## Sources

- `inception/requirements-analysis/requirements.md` (FR1, FR2.2–FR2.6, FR8.7, FR10, NFR1, NFR3)
- `inception/user-stories/stories.md` (US1.1–US1.4, US2.1–US2.4, US2.6, US8.4, US10.1)
- `inception/contract-design/contract-summary.md` C1, C2; `functional-design-questions.md` Q1–Q4
- `memory/project.md` M1, F2; `memory/team.md` Deployment and Code Style

```yaml
rules:
  - id: BR1.1
    statement: The signing secret is read from the environment each time a token is minted or verified; loading the auth code never reads it and never fails.
    category: constraint
    applies_to: TokenAuth
    trigger: mint, verify, or require_secret call
    logic: IF the auth code is loaded THEN read nothing; IF mint, verify or require_secret runs THEN read HSM_SIGNING_SECRET at that moment
    violation: loading fails before tests can set the secret (CQ-1)
    source: FR1.1
  - id: BR1.2
    statement: The auth code depends only on the standard library and the mock backend's own package.
    category: constraint
    applies_to: TokenAuth
    trigger: any change to the auth code
    logic: IF the auth code imports anything else THEN the import check fails
    violation: the import check fails
    source: FR1.5
  - id: BR1.3
    statement: A missing or empty secret is refused with an error naming HSM_SIGNING_SECRET.
    category: validation
    applies_to: SigningSecret
    trigger: require_secret, mint, verify
    logic: IF HSM_SIGNING_SECRET is unset or empty THEN raise SecretRefusal(reason=missing)
    violation: SecretRefusal
    source: FR1.2
  - id: BR1.4
    statement: A secret shorter than 32 UTF-8 bytes is refused; exactly 32 bytes is accepted.
    category: validation
    applies_to: SigningSecret
    trigger: require_secret, mint, verify
    logic: IF the UTF-8 byte length is under 32 THEN raise SecretRefusal(reason=too_short)
    violation: SecretRefusal
    source: FR1.2
  - id: BR1.5
    statement: No refusal message, log line or error ever contains the secret value.
    category: policy
    applies_to: SecretRefusal
    trigger: any refusal
    logic: IF a message is built THEN include the variable name and the rule broken, never the value
    violation: secret disclosure
    source: FR1.2, NFR1
  - id: BR1.6
    statement: There is no fallback or default secret anywhere, including local development and tests.
    category: policy
    applies_to: SigningSecret
    trigger: any code path that needs a secret
    logic: IF no secret is found THEN refuse; never substitute a value
    violation: an ungated process
    source: FR1.2, team.md Deployment
  - id: BR2.1
    statement: The burned literal and its scan exclusion leave in the same commit, which also carries the regression tests.
    category: policy
    applies_to: BurnedSecretExclusionList
    trigger: the commit that removes the literal
    logic: IF the literal is removed THEN TEMPORARY_EXCLUSIONS becomes empty in the same commit, and the burned value remains only in the permanent gitleaks allowlist and the check's own stand-in test value
    violation: the burned-secret check fails in CI
    source: FR1.3, M1
  - id: BR2.2
    statement: Each test run generates its own secret of at least 32 bytes and sets it before any server or subprocess starts; no fixed test secret is committed.
    category: policy
    applies_to: SigningSecret (source test_fixture)
    trigger: test session start
    logic: IF tests start THEN generate a fresh value and place it in the environment so subprocesses inherit it
    violation: tests depend on a developer's secret, or a secret is committed
    source: FR1.4
  - id: BR3.1
    statement: A local process with no secret in its environment reads HSM_SIGNING_SECRET from .env.local in the project root, without ever overriding a value already set.
    category: policy
    applies_to: LocalSecretFile
    trigger: start-up of the separate-process backend, the publish hook, or the MCP tool server
    logic: IF HSM_SIGNING_SECRET is unset AND .env.local exists AND contains the entry THEN set it for this process; IF it is already set THEN leave it; IF the file is absent THEN do nothing
    violation: the developer must export the secret by hand
    source: Q1, Q4 (changes team.md Deployment's "inherits it from the shell")
  - id: BR3.2
    statement: The dev-secret script writes a secret of at least 32 bytes into .env.local and refuses to replace an existing one without its overwrite option.
    category: policy
    applies_to: LocalSecretFile
    trigger: running scripts/dev-secret.sh
    logic: IF .env.local has HSM_SIGNING_SECRET AND --force is not given THEN exit non-zero and leave the file unchanged; ELSE write a fresh value
    violation: a developer's secret is silently replaced
    source: FR2.2, Q3
  - id: BR3.3
    statement: The start script loads .env.local when the variable is unset, refuses with a non-zero exit and a message when the secret is still missing or short, and accepts a port setting.
    category: validation
    applies_to: LocalSecretTooling
    trigger: running scripts/start_mock_server.sh
    logic: IF no valid secret after loading THEN print a message naming HSM_SIGNING_SECRET and exit non-zero without starting a server; IF a port is given THEN bind it
    violation: an ungated backend
    source: FR2.3
  - id: BR3.4
    statement: The separate-process backend refuses to start without a valid secret.
    category: validation
    applies_to: MockBackend
    trigger: python3 -m mock_hsm.server
    logic: IF require_secret fails after the local loader ran THEN exit non-zero with the message and serve nothing
    violation: a backend that serves requests that all fail
    source: FR2.3, contract C1
  - id: BR3.5
    statement: A request to a running backend that finds the secret missing or invalid gets HTTP 503 with a JSON error naming HSM_SIGNING_SECRET; the backend keeps serving.
    category: policy
    applies_to: MockBackend
    trigger: token verification during a request
    logic: IF verify raises SecretRefusal THEN respond 503 with the message and never the value
    violation: an unhandled error, or a leaked secret
    source: Q2, contract-design finding R-06
  - id: BR4.1
    statement: The publish hook denies publish_schedule explicitly, naming the missing secret, when it can't obtain a valid one; with a valid secret and a compliant schedule it falls through as today.
    category: authorization
    applies_to: PublishHook
    trigger: a publish_schedule call
    logic: IF require_secret fails THEN deny with a reason naming HSM_SIGNING_SECRET; ELSE validate as today
    violation: a crashed hook fails open
    source: FR2.4
  - id: BR4.2
    statement: Every MCP tool returns a tool error naming HSM_SIGNING_SECRET when no valid secret is available; .mcp.json never holds a secret.
    category: validation
    applies_to: McpTools
    trigger: any mcp__hsm__* call
    logic: IF require_secret fails THEN return a tool error with the message
    violation: an opaque failure, or a committed secret
    source: FR2.5
  - id: BR5.1
    statement: .streamlit/secrets.toml, .env, .env.local and .env.* are ignored by explicit .gitignore lines outside the AI-DLC-managed block.
    category: policy
    applies_to: repository configuration
    trigger: any commit
    logic: IF one of those paths exists THEN git ignores it
    violation: a committed secret
    source: FR2.6, F2
  - id: BR5.2
    statement: The two broad catches in the project hooks carry a noqa reason.
    category: policy
    applies_to: PublishHook, lint hook
    trigger: code review
    logic: IF a noqa BLE001 appears THEN it carries "-- <reason>"
    violation: the team code-style rule is broken
    source: FR8.7
  - id: BR6.1
    statement: The docs describe setting the secret with the dev-secret script, how claude-launched tools get it (from .env.local, per BR3.1), and the start command; none says there is no password; each doc change ships with the change it describes.
    category: policy
    applies_to: documentation
    trigger: this unit's pull request
    logic: IF behaviour changes THEN the matching docs section changes in the same pull request
    violation: a fresh clone can't start
    source: FR10.1
```

## Rules Summary

| ID | Rule | Category |
|----|------|----------|
| BR1.1 | Secret read when used, never when the code loads | constraint |
| BR1.2 | Auth code depends only on the standard library and `mock_hsm` | constraint |
| BR1.3 | Missing or empty secret refused, naming the variable | validation |
| BR1.4 | Under 32 bytes refused; exactly 32 accepted | validation |
| BR1.5 | No message ever contains the value | policy |
| BR1.6 | No fallback secret anywhere | policy |
| BR2.1 | Literal and exclusion removed together, with regression tests | policy |
| BR2.2 | Tests generate their own secret per run | policy |
| BR3.1 | Local processes read `.env.local` when the variable is unset; never override | policy |
| BR3.2 | Dev-secret script never overwrites without `--force` | policy |
| BR3.3 | Start script loads, checks and refuses; accepts a port | validation |
| BR3.4 | Separate-process backend refuses to start without a secret | validation |
| BR3.5 | Mid-run secret failure answers 503, naming the variable | policy |
| BR4.1 | Hook denies explicitly without a secret | authorization |
| BR4.2 | MCP tools return a clear error; no secret in `.mcp.json` | validation |
| BR5.1 | Secret files ignored explicitly | policy |
| BR5.2 | `noqa` reasons on broad catches | policy |
| BR6.1 | Docs updated with each change | policy |

## Assumptions & Open Questions

- BR3.1 changes the affirmed team rule in `team.md` Deployment ("the MCP server inherits it from the shell"). The change is persisted through this stage's learnings step, not by editing the file directly (Q4).
