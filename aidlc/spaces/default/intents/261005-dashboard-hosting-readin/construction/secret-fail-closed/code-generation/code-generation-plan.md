# Code Generation Plan — U1 secret-fail-closed

## Sources

- `functional-design/` (entities.md, rules.md BR1.1–BR6.1, functional-spec.md W1–W9, traceability.json with 29 ACs)
- `nfr-requirements/security-requirements.md` (NFR1.1–NFR7.1), `nfr-design/security-design.md` (D1–D5), `infrastructure-design/cicd-pipeline.md`
- `inception/contract-design/contract-summary.md` C1, C2; `inception/units-generation/unit-of-work.md` (U1: US1.1–US1.4, US2.1–US2.4, US2.6, US8.4, US10.1)
- The open review items from the functional-design, NFR and infrastructure-design reviews (all resolved below under Design Decisions)
- Current code at `825a0f8`: `mock_hsm/auth.py`, `mock_hsm/server.py` (`_dispatch`, `run`, `__main__`), `scripts/start_mock_server.sh`, `scripts/check_burned_secret.py`, `.gitleaks.toml`, `.claude/hooks/require_no_violations.py`, `.claude/hooks/lint_before_commit.py`, `mcp_server/hsm_tools.py`, `.mcp.json`, `.gitignore`, `tests/conftest.py`, `.github/workflows/ci.yml`

## Design Decisions Settled in This Plan

| # | Decision | Resolves |
|---|----------|----------|
| P1 | `require_secret() -> None` keeps contract C1's signature. A private `_secret_bytes()` does the checks and returns the value, and `mint_token`/`verify_token` call it. | The difference between C1 (`-> None`) and the NFR design sketch (`-> bytes`) |
| P2 | `mint_token` keeps raising `ValueError` for an unknown user, as today. C1's "KeyError" was a wording error; changing it would break existing callers. | C1 wording |
| P3 | The burned-value refusal compares SHA-256 against `BURNED_SECRET_SHA256` in `auth.py`, which equals the constant in `scripts/check_burned_secret.py` and is already allowlisted in `.gitleaks.toml`. The regression test reads the burned value from `.gitleaks.toml`, which is permanently excluded from the scan, so no tracked test file holds the literal. A second test asserts the two hash constants are equal. | NFR review R-03; NFR design review R-01 |
| P4 | The local loader skips `.env.local` whenever `HSM_SIGNING_SECRET` is **present** in the environment, even if empty. An empty value is then refused as `missing`. Subprocess tests use this to simulate a missing secret without touching a developer's real `.env.local`. | Test isolation for the hook, MCP and server tests |
| P5 | The start script becomes `exec python3 -m mock_hsm.server "$@"`. Python's `load_local_secret()` is the only `.env.local` parser, so the script never sources the file. | NFR design review R-02 (BR3.3's "loads .env.local" is met by Python) |
| P6 | `scripts/dev-secret.sh` accepts `--file PATH` (default `<repo>/.env.local`) so tests write to a temporary file. | Test isolation |
| P7 | The hook's `mock_hsm.auth` import already sits inside `main()`, under the `__main__` catch-all that denies. The secret check is added after the tool-name check (other tools still fall through) and before validation. | NFR design review R-03 |
| P8 | The 503 warning logs `urlparse(self.path).path`, never the query string. | NFR design review R-05 |
| P9 | The local dashboard (`streamlit run`) gets the secret from the shell until U3's SecretsBridge lands. The docs show how to export it from `.env.local`. | NFR design review R-04 |

## Code Generation Steps

Each behaviour follows Red (write failing tests, run them, record the failing output), Green (the least code that passes), then Refactor (with the suite green). The new tests go in two files: `tests/test_signing_secret.py` (auth module and loader) and `tests/test_secret_entry_points.py` (processes, scripts and configuration).

- [x] **Step 1 — Runner check.** Run the unit command from `unit-test-instructions.md` against the existing suite to confirm the runner works. Record the baseline: tests collected and passed.
- [x] **Step 2 — Test-session secret (US1.4; BR2.2; NFR3.2).**
  - Red: tests that `HSM_SIGNING_SECRET` is set to at least 32 bytes during tests, and that two calls of the conftest generator differ.
  - Green: `tests/conftest.py` sets `os.environ["HSM_SIGNING_SECRET"] = secrets.token_urlsafe(32)` at module import, before any `mock_hsm` import. It always overwrites, so a developer's shell secret is never used.
- [x] **Step 3 — Hook deny, tested first (US2.3; BR4.1; NFR1.4).**
  - Red: run the hook as a subprocess with a `publish_schedule` payload and `HSM_SIGNING_SECRET=""`. Expect a deny whose reason names `HSM_SIGNING_SECRET` and does not contain the value. A non-publish payload still falls through.
  - Green comes in Step 7.
- [x] **Step 4 — Secret gate in `mock_hsm/auth.py` (US1.1, US1.2; BR1.1–BR1.6; NFR1.2, NFR1.3, NFR1.6, NFR1.7).**
  - Red tests:
    - importing the module with the variable unset raises nothing;
    - `require_secret()` refuses with reason `missing` when unset or empty, `too_short` at 31 bytes (counted in UTF-8 bytes, including a multi-byte case) and `burned` for the burned value (P3), and accepts exactly 32 bytes;
    - `SecretMissingError` is a `RuntimeError` and not a `TokenError`;
    - every message names `HSM_SIGNING_SECRET` and never contains the value;
    - `mint_token` and `verify_token` refuse without a secret;
    - a token minted under one secret fails verification under another (the secret is read on every call);
    - `auth.BURNED_SECRET_SHA256` equals the constant in the check script;
    - an AST check that the module imports only the standard library and `mock_hsm`.
  - Green: `SECRET_ENV`, `MIN_SECRET_BYTES = 32`, `BURNED_SECRET_SHA256`, `SecretMissingError(reason)`, `require_secret()`, `_secret_bytes()`. `mint_token` and `verify_token` use `_secret_bytes()`. The `_SECRET` literal stays, unused, until Step 13.
- [x] **Step 5 — Local loader `load_local_secret(path=None)` (US2.2; BR3.1; NFR1.10).**
  - Red tests, using temporary files:
    - with the variable unset and a file entry, the variable is set;
    - an already-set value, including an empty one, is kept (P4);
    - a missing file and a missing line are both no-ops;
    - other lines are ignored;
    - one pair of matching quotes is stripped;
    - `$HOME` and backticks are taken literally;
    - the default path resolves from `auth.py`'s location, not the working directory;
    - the value is never printed.
  - Green: the loader in `mock_hsm/auth.py`.
- [x] **Step 6 — Backend start and 503 (US2.2; BR3.4, BR3.5; NFR1.5).**
  - Red tests:
    - `python3 -m mock_hsm.server --port <free>` with `HSM_SIGNING_SECRET=""` exits 1, names the variable, and nothing listens;
    - with a valid secret it listens on the given port;
    - `--port abc` is a usage error with exit 2;
    - in-process (port 0): clearing the secret mid-run gives 503 with a JSON error naming the variable for a protected GET (the verify path) and for `POST /sessions` (the mint path); the server keeps serving; one stderr warning holds the path without the query string (P8) and never the value.
  - Green:
    - `__main__` parses `--port` with `argparse` (default 8770), then calls `load_local_secret()` and `require_secret()`, printing the message and exiting 1 on a refusal;
    - `_dispatch` catches `SecretMissingError` around both `verify_token` and the handler call, ahead of the generic 500 handler.
- [ ] **Step 7 — Hook green, plus `noqa` reasons (US2.3, US8.4; BR4.1, BR5.2).**
  - Green for Step 3: `require_no_violations.py` calls `load_local_secret()` and then `require_secret()` after the tool-name check and before validation, and denies with the message.
  - Both broad catches gain reasons: `require_no_violations.py` and `lint_before_commit.py` each get `# noqa: BLE001 -- <reason>`.
  - The existing tests in `tests/test_hooks.py` still pass.
- [x] **Step 8 — Start script (US2.2; BR3.3).**
  - Red: subprocess tests of `scripts/start_mock_server.sh --port <free>`. With `HSM_SIGNING_SECRET=""` it exits non-zero with the message; with a secret it listens.
  - Green: the script runs `exec python3 -m mock_hsm.server "$@"` (P5). Update its header comment.
- [x] **Step 9 — MCP tools (US2.4; BR4.2; NFR1.8).**
  - Red tests:
    - with `HSM_SIGNING_SECRET=""`, `_client()` raises a `SecretMissingError` naming the variable; FastMCP returns this as a tool error;
    - `.mcp.json` holds no `HSM_SIGNING_SECRET`.
  - Green: `hsm_tools.py` calls `load_local_secret()` under `__main__` before `mcp.run()`. `tests/test_mcp_tools.py` keeps passing.
- [x] **Step 10 — Dev-secret script (US2.1; BR3.2; NFR1.9).**
  - Red tests, using `--file <tmp>`:
    - a new file gets mode 600 and a value of at least 32 bytes;
    - two runs without `--force` leave the file unchanged, exit non-zero and print the "already set" message;
    - `--force` replaces the value, keeps the other lines, and results in mode 600 even when the file was 644.
  - Green: `scripts/dev-secret.sh` (bash, `umask 077`, `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`, `chmod 600` after every write; executable bit set).
- [x] **Step 11 — Repository hygiene (US2.6; BR5.1; NFR1.9).**
  - Red: a test runs `git check-ignore` on `.env`, `.env.local`, `.env.prod` and `.streamlit/secrets.toml`, and checks that the lines appear above the `# BEGIN AI-DLC:gitignore` marker.
  - Green: add the explicit lines to `.gitignore`.
- [x] **Step 12 — CI step and docs (US10.1; BR6.1; infrastructure-design Q1).**
  - CI: in `.github/workflows/ci.yml`, add a named first step in the `tests` job, after checkout and setup. It fails, naming the variable, if `HSM_SIGNING_SECRET` is non-empty. It is a plain `run` step with no new action or permission. Run `scripts/check_workflows.py` and its tests.
  - Docs: update `CLAUDE.md` (Commands and Running the workflows: `scripts/dev-secret.sh`, then the start command; the hook and MCP server read `.env.local`; how to export the secret for the local dashboard, per P9), `README.md`, and `dashboard/README.md` if it shows a start command. Remove any "no password" wording.
- [x] **Step 13 — Remove the burned literal (US1.3; BR2.1; NFR1.1, NFR1.7). This must be the last code change.**
  - Red: a test that `mock_hsm/auth.py` no longer contains `_SECRET =`, and that `TEMPORARY_EXCLUSIONS` is empty. Also a test that `require_secret()` refuses the burned value read from `.gitleaks.toml` (P3), if Step 4 did not already cover it.
  - Green:
    - delete the literal;
    - set `TEMPORARY_EXCLUSIONS = ()`;
    - update the existing burned-secret check tests that assume the old exclusion;
    - `python3 scripts/check_burned_secret.py` prints `burned secret: ok`.
- [x] **Step 14 — Verification and traceability.**
  - Run the unit command, then the full suite `python3 -m pytest tests/ -q`, `ruff check .`, `ruff format --check .` and `coverage run -m pytest tests/ -q && coverage combine -q && coverage report`.
  - The test count stays at or above `.test-floor` and coverage stays at or above `.coverage-floor`. Neither floor file is edited.

## Commits and Pull Request

After generation, the human is asked before each commit. Every commit goes through `/commit`, on branch `secret-fail-closed` created from `main`:

1. **Commit A:** Steps 2–12 together with their tests.
2. **Commit B:** Step 13 alone, together with its tests. It is created only after commit A, so the literal leaves last, in one commit with the exclusion (M1).

Pull request 1 is opened only after Build and Test. AI-DLC record files are not part of these commits.

## Story Traceability

| Story | Steps |
|-------|-------|
| US1.1 Secret read at use | 4 |
| US1.2 Refuse missing or short | 4 |
| US1.3 Burned literal removed | 13 |
| US1.4 Tests bring their own secret | 2 |
| US2.1 Dev-secret script | 10 |
| US2.2 Local start fails closed | 5, 6, 8 |
| US2.3 Hook denies | 3, 7 |
| US2.4 MCP tool error | 9 |
| US2.6 Secret files ignored | 11 |
| US8.4 `noqa` reasons | 7 |
| US10.1 Docs | 12 |

## Assumptions & Open Questions

- Tests that rely on `auth._SECRET` directly, if there are any, are switched to the environment secret in the step that changes that behaviour.

## Testing Contract

```json
{
  "version": 1,
  "methodology": "tdd",
  "source": "team",
  "ordering": "For each behaviour, write a failing test first, then write only the code that makes it pass, then refactor with the suite green.",
  "scope": "feature",
  "test_strategy": "standard",
  "project_type": "brownfield",
  "applicable_notes": [
    {
      "layer": "org",
      "text": "We treat tests as a first-class deliverable in every Bolt. The specific\nmethodology (TDD, BDD, ATDD, or classic test-after) is affirmed at\npractices-discovery and recorded in `team.md` under this heading with explicit\n`Methodology` and `Ordering` fields; Code Generation resolves those fields\nindependently from coverage, tooling, and scope notes.\n\nWhen no posture has been affirmed, our default per scope is:\n- **Methodology**: test-after\n- **Ordering**: implement each applicable testable layer, then write and run\n  that layer's tests.\n- `mvp`, `enterprise`, `feature`, `infra`, `classic` add an 80% line-coverage\n  floor and CI execution before merge.\n- `bugfix`, `security-patch` add a targeted regression for the specific\n  bug/vulnerability and require the existing suite to remain green.\n- `express` uses the Minimal strategy: requirement-driven unit tests (one per\n  requirement, with a happy-path floor per component); existing tests remain\n  green.\n- `poc`, `refactor`, `workshop` add no extra new-test floor and require the\n  existing suite to remain green.\n\nThe active `Test Strategy` still applies in every scope and determines test\nvolume/types. Scope floors are additive; they never reduce or replace the\nselected strategy.\n\nBuild and Test verifies defined coverage floors and affirmed quality targets;\nthey may not be weakened to make a step pass.\n\nAffirm a stricter posture in `team.md` if the team commits to one."
    },
    {
      "layer": "team",
      "text": "- **Methodology**: tdd\n- **Ordering**: For each behaviour, write a failing test first, then write only the code that makes it pass, then refactor with the suite green.\n- Tests ship in the same commit as the code they cover.\n- **Coverage**: line coverage is measured over `agents/`, `dashboard/`,\n  `mock_hsm/`, `mcp_server/` and `.claude/hooks/`, with `tests/` excluded and\n  subprocess measurement switched on (`.coveragerc`). `scripts/` is not\n  measured; its scripts are held to their own tests instead. Coverage is\n  measured on the gate Python leg (3.14) only. CI enforces the floor in\n  `.coverage-floor` and, while that floor is at least 80, the 80% gate as well.\n  Every new module under the measured packages counts toward the floor.\n- **Test count**: `.test-floor` is the minimum number of passing tests, with no\n  failures, that CI accepts in every leg of the Python matrix.\n- Both floor files only rise; a pull request that lowers either one fails CI.\n  The floors and the measured package set are never lowered or narrowed to get\n  a run to pass, including through `# pragma: no cover` or a `.coveragerc`\n  omit. At the end of an intent, Build and Test re-measures and raises both\n  floor files, keeping some headroom, in the intent's final pull request.\n  Measured figures live in the practices-discovery evidence, not in this file.\n- CI runs the suite on a Python matrix of 3.10 (the declared floor) and 3.14\n  (the version we develop on). Both must pass before merge. When the\n  repository variable `HOSTED_PYTHON` is set to another version (the Python the\n  hosted app runs on), CI adds it to the matrix.\n- CI runs the suite with plain `python -m pytest tests/`. It never passes an\n  unrelated `-m` expression, because any `-m` switches off the default `perf`\n  skip in `tests/conftest.py`.\n- The `perf`-marked timing tests never run in CI. They run by hand with\n  `-m perf` when someone wants them. No test carries both the `perf` and the\n  `browser` mark, and a test checks this.\n- **Browser tests**: `browser`-marked tests need Playwright and Chromium. They\n  are skipped unless the `-m` expression names `browser`, and they run in the\n  required `browser-tests` job with `-m browser`. On a pull request they run\n  only against an app started inside the job on loopback, with the identity\n  provider replaced by a test double; staging is reached only by the\n  post-deploy check. They do not count toward `.test-floor`.\n- **`browser-tests` cannot pass without testing**: it runs on every pull\n  request and skips the browser run only when no watched file changed. The\n  watch list covers `scripts/postdeploy_check.py`, `dashboard/markers.py`,\n  `dashboard/auth_gate.py`, `agents/build_info.py`, `tests/*browser*`,\n  `requirements-dev.txt` and `.github/workflows/ci.yml`. A meta-test fails when\n  a browser test file, or a source file it imports, is off the watch list. Once\n  the first browser test exists, the job no longer accepts \"no tests ran\" as a\n  pass, and it gets the same single retry as the `tests` jobs.\n- A flaky test may be retried once in CI. A test that fails on the retry\n  blocks the merge.\n- The suite runs serially. The fixed ports 8772 and 8773 in\n  `test_mcp_tools.py` and `test_hooks.py` make `pytest-xdist` (`-n`) unsafe, so\n  we do not parallelise until those ports are made ephemeral. New tests that\n  start a server bind port 0 and read back the assigned port; they never add a\n  fixed port.\n- **Signing secret in tests**: `tests/conftest.py` generates a throwaway\n  secret per run and puts it in `os.environ` before any server or subprocess\n  starts, so subprocess tests inherit it. No fixed test secret is committed.\n- Every test's audit trail goes to a temp file through `HSM_AUDIT_PATH`\n  (`tests/conftest.py`). CI does not export `HSM_BASE_URL`,\n  `HSM_ACTIVE_USER`, `HSM_AUDIT_PATH` or a signing secret of its own.\n- **Gate behaviour is tested first.** A hook or gate that cannot obtain the\n  signing secret denies explicitly, and a failing test proves that before the\n  code changes, because a crashed hook fails open. The sign-in decision is a\n  pure function, unit-tested without Streamlit, and the dashboard wiring is\n  tested with `AppTest` through a fake identity, asserting that no tab and no\n  persona picker renders before the gate allows. The demo-data reset banner is\n  a tested requirement.\n- New pipeline helper scripts (such as the post-deploy check) get their own\n  tests: the happy path plus at least two error cases."
    },
    {
      "layer": "project",
      "text": "- With no requirements or NFR artifacts in this workflow, the target inventory was built from the Testing Contract and the unit-test instructions' coverage targets, and cross-unit traceability used the plan's own R1-R8. (learned 2026-10-04) \n\n- Initial CI floors are set with headroom below the local measurement (coverage floor 95.00 against 96%, test floor 745 against 811 passing) so runner differences don't fail the first run; floors only ever rise afterwards. (learned 2026-10-04)"
    }
  ],
  "obligations": {
    "strategy": "standard",
    "strategy_volume": [
      "Five to eight tests per component.",
      "Unit tests plus integration tests for key boundaries.",
      "Add E2E, performance, or security tests when requirements demand them."
    ],
    "scope_floor": [
      "Meet an 80% line-coverage floor.",
      "Run the selected tests in CI before merge."
    ],
    "combination_rule": "Apply every selected-strategy obligation and every scope-floor obligation; neither replaces the other, and a targeted scope regression may add the narrowest necessary test type beyond the strategy default."
  },
  "plan_profile": {
    "methodology": "tdd",
    "runner_step": "Verify the existing test runner/configuration and record the exact unit-scoped command.",
    "runner_ready_before_first_test": true,
    "testable_layers": [
      "Data model / database behavior",
      "Repository / data access",
      "Business logic",
      "API / endpoint",
      "Frontend behavior"
    ],
    "steps": [
      "Project structure and production configuration skeleton.",
      "Verify the existing test runner/configuration and record the exact unit-scoped command.",
      "Data model / database behavior - Red: write the failing tests and record the failing command output.",
      "Data model / database behavior - Green: implement only enough behavior to pass.",
      "Data model / database behavior - Refactor: improve the implementation while tests stay green.",
      "Repository / data access - Red: write the failing tests and record the failing command output.",
      "Repository / data access - Green: implement only enough behavior to pass.",
      "Repository / data access - Refactor: improve the implementation while tests stay green.",
      "Business logic - Red: write the failing tests and record the failing command output.",
      "Business logic - Green: implement only enough behavior to pass.",
      "Business logic - Refactor: improve the implementation while tests stay green.",
      "API / endpoint - Red: write the failing tests and record the failing command output.",
      "API / endpoint - Green: implement only enough behavior to pass.",
      "API / endpoint - Refactor: improve the implementation while tests stay green.",
      "Frontend behavior - Red: write the failing tests and record the failing command output.",
      "Frontend behavior - Green: implement only enough behavior to pass.",
      "Frontend behavior - Refactor: improve the implementation while tests stay green.",
      "Environment/build configuration.",
      "Documentation and traceability."
    ]
  },
  "input_sha256": "sha256:ed1172a231d8ff0fee1c6e3eb2c1f66689d445beb7466da34df8c830cbd54159",
  "contract_sha256": "sha256:a73ec1a748dc439c0dd9c9de5fc8ccef200edbba9c8676d7d802f32eaf4cf117"
}
```
