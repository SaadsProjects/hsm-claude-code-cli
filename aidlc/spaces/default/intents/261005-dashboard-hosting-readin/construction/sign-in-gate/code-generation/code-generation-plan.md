# Code Generation Plan — U3 sign-in-gate

## Sources

- `functional-design/` (rules.md BR1.1–BR7.1; functional-spec.md W0–W5 and the VisitorAccess state machine; frontend-components.md; entities.md; 27 ACs AC2.5.1–AC8.1.1)
- `nfr-requirements/` (NFR1.21–NFR1.28, NFR2.11–NFR2.13, NFR3.11, NFR4.11, NFR5.11, NFR7.11)
- `nfr-design/` (S1–S8, P1–P3, logical-components) and its review's items R-01–R-06, settled below
- `infrastructure-design/` (signing-secret sources Q1 A, no CI change Q2 A, local run, rollback) and its review's items R-01–R-03, settled below
- `inception/contract-design/contract-summary.md` C1, C3, C4, C5, C6, C7; `inception/units-generation/unit-of-work.md` U3 and `unit-of-work-story-map.md` (US2.5, US4.1–US4.8, US8.1, plus U3's share of US10.1 docs)
- Current code: `dashboard/app.py` (`_page_header`, `main`, `run`, `_login_panel`, `_session_panel`, `PERSONA_KEY`), `dashboard/session.py` (`LOGIN`, `NOTICE`, `SCOPED_DEFAULTS`, `FORM_KEY_PREFIX`, `clear_session_scoped`, `client_for`), `dashboard/actions.py` (`log_out`, `clear_cached_reads`), `dashboard/safe_text.py`, `mock_hsm/auth.py` (`require_secret`, `load_local_secret`, `SecretMissingError`, `SECRET_ENV`), `mock_hsm/embedded.py`, `tests/test_dashboard_app.py` (`app` fixture), `tests/test_dashboard_data.py` (`_run_app`), `tests/test_dashboard_embedded.py` (`_render`), `tests/conftest.py`, `requirements.in`, `.gitignore`, `.streamlit/config.toml`

## Design Decisions Settled in This Plan

| # | Decision | Resolves |
|---|----------|----------|
| D1 | `dashboard/app.py` owns the page header. `run()` calls `_page_header()` once, first, on every path. `main()` stops calling it, and the gate never calls `st.set_page_config` or `st.title`. The `render_page_header()` line in security-design S3's sketch is superseded by this decision | NFR-design review R-02 (Major) |
| D2 | `end_visitor_session()` does the backend call inside `try`, and the state clearing in `finally`. It catches by name `BackendNotRunning`, `HsmApiError` (which covers `HsmUnavailable`), `SecretMissingError` and `KeyError` (an unknown user in `mint_token`), and logs only the type. Any other error still clears the state and is then re-raised unchanged | NFR-design review R-01 (Major) |
| D3 | The visitor's email is drawn with `st.text`, which never interprets Markdown or HTML: "Signed in as: " plus the raw email on Screen 2, and the raw email in the Account section. Tests assert the element's value is exactly the raw string | NFR-design review R-03 |
| D4 | `gate()` draws every gate screen inside one `st.empty()` placeholder. Screen 5 replaces the placeholder's content, so an error part-way through drawing Screen 1 or 2 leaves only Screen 5 on the page | NFR-design review R-04 |
| D5 | The account binding stores the trimmed, lower-cased email. The first allowed rerun only binds. A later allowed rerun with a different normalised email runs `end_visitor_session()` and then binds the new one | NFR-design review R-05 |
| D6 | The shared helper lives in `tests/gate_app.py` (not collected as tests). Its own test is written first: `AppTest` secrets with nested `auth` and `auth.google` mappings reach `st.secrets` inside the script. If they don't, the helper patches `secrets_bridge.read_hosted_secrets` instead, and nothing else in the plan changes | NFR-design review R-06 |
| D7 | `auth_gate` sets its logger `dashboard.auth_gate` to INFO at import, so INFO refusal lines are emitted without any root configuration. A test captures one | Infrastructure review R-01 |
| D8 | Markers: each gate screen is `st.container(key=<marker>)`, and each button uses its marker as its widget key. `markers.py` holds `str` constants only, with `from __future__ import annotations` as its only import | C6, BR4.7 |
| D9 | The bridge's signing-secret order: an exported value, then `st.secrets["HSM_SIGNING_SECRET"]` when the variable is unset or empty, then `mock_hsm.auth.load_local_secret()`. The hosted read is guarded, so unreadable secrets count as absent (BR1.5). `.streamlit/secrets.toml.example` carries `HSM_SIGNING_SECRET` only as a comment | Infrastructure Q1 A |
| D10 | The seam reads `st.user.is_logged_in`, `st.user.get("email")` and `st.user.get("email_verified")` and passes the raw verified value through unchanged. `sign_in()` calls `st.login("google")` and `sign_out()` calls `st.logout()` | C4, S2 |
| D11 | Screen 4 (backend failed) gains the Account section in the sidebar, drawn by `auth_gate.render_account_section`. `main()` draws the Account section first in the sidebar, then a divider and the "Demo persona" heading above the existing persona panel. The persona caption reads "Acting as …" | BR4.6, AC3.3.2 |
| D12 | Work stays on the intent branch `dashboard-hosting`. No push, draft pull request or commit happens without the human's go-ahead. The commit goes through `/commit` | team.md Way of Working; project.md Mandated |

## Code Generation Steps

Each behaviour follows Red (write the failing tests, run them, record the failing output), then Green (the least code that passes), then Refactor (with the suite green). The Red output for each step is recorded in `code-summary.md`.

- [x] **Step 1 — Branch, runner and baseline.** On `dashboard-hosting`, run `python3 -m pytest tests/test_dashboard_app.py tests/test_dashboard_data.py tests/test_dashboard_embedded.py -q` and the full suite `python3 -m pytest tests/ -q` once. Record the counts, which are the baseline for AC4.8.2.
- [x] **Step 2 — Dependency (US8.1; AC8.1.1; NFR7.11; S8).** Change `streamlit==1.64.0` to `streamlit[auth]==1.64.0` in `requirements.in`. Recompile both locks with the `uv pip compile` commands at the top of `requirements.in` and `requirements-dev.in`, then install with `pip install --require-hashes -r requirements-dev.txt`. Check that `import authlib` works and that `requirements.txt` pins Authlib with hashes. Run `pip-audit` if it is installed locally. CI's `audit` job is authoritative.
- [x] **Step 3 — Shared test helper (D6; AC4.8.1; NFR3.11).**
  - Red: `tests/test_gate_app.py` builds an app through `gate_app()` from a tiny script that writes `st.secrets["auth"]["google"]["client_id"]` and `st.secrets["HSM_ALLOWED_EMAILS"]`. It asserts the values arrive, and that the seam patch is in place (`auth_gate.current_identity()` returns the fake identity).
  - Green: `tests/gate_app.py` has `ALLOWED_EMAIL`, `DUMMY_AUTH` (the five keys with placeholder values), `allowed_identity()`, `identity(...)` and `gate_app(path, monkeypatch, identity=..., secrets=..., timeout=30)`. The helper sets `at.secrets`, patches `auth_gate.current_identity`, `sign_in` and `sign_out`, and returns the `AppTest`. The patch targets come into existence in Step 4.
- [x] **Step 4 — Pure decision core (US4.5; AC4.5.1, AC4.5.2, AC4.2.1, AC4.3.1, AC4.3.2; BR2.2, BR2.3, BR3.1–BR3.5; NFR1.22, NFR1.23; S2).**
  - Red, in `tests/test_auth_gate.py`:
    - `parse_allowlist`: a valid list is trimmed and lower-cased; a missing value, a plain string, an empty list, a non-string entry and a blank entry each raise `AllowlistInvalidError`.
    - `decide`: allowed; not signed in; signed in with no email or a blank email gives `gate_error`; `email_verified` of `False`, missing, `None`, `"true"`, `"false"` and `1` each give `not_verified`; an unlisted email gives `not_listed`; a domain-only entry `example.com` never matches `a@example.com`; mixed case and surrounding spaces match.
    - An AST test shows `decide` and `parse_allowlist` call no `st.` attribute.
  - Green: `dashboard/auth_gate.py` with `Identity`, `Decision` (frozen dataclasses), the outcome and reason constants, `AllowlistInvalidError`, `parse_allowlist` and `decide`.
- [x] **Step 5 — Markers (BR4.7; C6).**
  - Red: `markers.py` defines the 10 C6 names as distinct non-empty `str` values, and its only import is `__future__`.
  - Green: `dashboard/markers.py`.
- [x] **Step 6 — Secrets bridge (US2.5; AC2.5.1–AC2.5.4; BR1.1–BR1.5; NFR1.25; S4; D9).**
  - Red, in `tests/test_secrets_bridge.py`:
    - an exported value is never overwritten by a different hosted one;
    - a hosted value is copied when the variable is unset and when it is empty, and `mint_token` and `verify_token` then round-trip;
    - with neither source set, `.env.local` is read through `load_local_secret` (the path is patched to a temp file); a value that is present is never replaced;
    - unreadable hosted secrets (the read raises) count as absent;
    - `cookie_secret_conflict(...)` is true only for equal non-empty values;
    - a scan shows `mock_hsm/` still imports no Streamlit.
  - Green: `dashboard/secrets_bridge.py` with `read_hosted_secrets()` (guarded `st.secrets.to_dict()`, `{}` on error), `bridge_signing_secret(hosted)` and `cookie_secret_conflict(signing, cookie)`, using `hmac.compare_digest`.
- [x] **Step 7 — Gate evaluation and fail-closed order (US4.4; AC4.4.1–AC4.4.3; BR1.2, BR1.3, BR2.1, BR3.6, BR3.7; NFR1.24; S3).**
  - Red: `evaluate(hosted, identity_reader)` returns `settings_missing` for:
    - a missing or short secret;
    - a secret equal to the cookie secret;
    - each of the five keys missing, blank or not a string;
    - a missing `auth` or `auth.google` section.

    It returns `allowlist_invalid` for a bad allowlist. It never calls `identity_reader` before those checks pass, so the order is fixed.
  - Green: `_evaluate` in `auth_gate`.
- [x] **Step 8 — Refusal logging (US4.7; AC4.7.1, AC4.7.2; BR6.1–BR6.3; NFR4.11, NFR1.26; S7; D7).**
  - Red, with `caplog` on `dashboard.auth_gate` and a plain-dict state:
    - one line per reason across repeated calls;
    - INFO for `not_verified` and `not_listed`, WARNING for `settings_missing`, `allowlist_invalid` and `gate_error`;
    - nothing for `not_signed_in`;
    - the `gate_error` line names the type only;
    - the `settings_missing` line for a cookie clash names both settings;
    - no line contains the email, either secret or an allowlist entry;
    - after the marks are cleared, a reason is logged again;
    - the logger's level is INFO with no root configuration.
  - Green: `_log_refusal_once(decision, state, error_type=None, settings=())`.
- [x] **Step 9 — Gate screens and the dashboard wiring (US4.1, US4.2, US4.3; AC4.1.1–AC4.1.5, AC4.2.2, AC4.3.3, AC4.4.2, AC4.4.3; BR4.1–BR4.5; NFR1.21, NFR1.24, NFR1.26, NFR1.27, NFR5.11; S1, S3, S5; D1, D3, D4, D8).**
  - Red, in `tests/test_dashboard_gate.py`, through `gate_app`:
    - signed out: Screen 1 has the exact copy and the `SIGN_IN_BUTTON`, and pressing it calls the patched `sign_in`;
    - not listed and not verified: Screen 2 has the exact copy, the email as raw text and Sign out;
    - each of settings missing, allowlist invalid, cookie clash and a `decide` that raises gives Screen 5 with the exact copy;
    - Screen 5 shows Sign out when signed in, and none when the identity read raises;
    - every refusal path: one h1, no tabs, no persona or site widget, and a spy on `embedded.start` never called;
    - the markup emails `<b>x</b>@example.com` and `*a*@example.com` appear as the literal string;
    - an error raised while Screen 2 is being drawn leaves only Screen 5;
    - a test pins that `StopException` and `RerunException` are not `Exception` subclasses.
  - Green: `gate(state=None)`, the three screen functions and `render_account_section` in `auth_gate`, plus the seam. In `app.py`, `run()` becomes: `_page_header()`, `secrets_bridge` plus `auth_gate.gate()`, then `st.stop()` unless allowed, then the existing embedded start, Screen 4 and `main()`.
- [x] **Step 10 — Signed-in frame (US4.6; AC4.6.1; BR4.6; D11).**
  - Red, through `gate_app`, allowed:
    - the sidebar's first block is the Account section with the email and Sign out;
    - then a divider, "Demo persona" and the persona login;
    - after a persona login, the caption reads "Acting as …";
    - Screen 4 (start forced to fail) shows the Account section and no persona section.
  - Green: `main()` and Screen 4 in `app.py`.
- [x] **Step 11 — Sign-out and account binding (AC4.6.2, AC4.6.3; BR5.1, BR5.2; NFR1.28; S6; D2, D5).**
  - Red:
    - Sign out after a persona login: `sign_out` is called; the session holds no login, notice, scoped item, `form:` key, refusal mark or binding; and the backend session ended (its status is no longer valid).
    - Sign out with the backend call raising each of `HsmUnavailable`, `HsmApiError`, `BackendNotRunning` and `SecretMissingError` still clears the state.
    - Any other error still clears the state and is re-raised.
    - `sign_out` raising is logged as `gate_error`, and the state stays cleared.
    - An allowed rerun with a different email (case changes alone don't count) clears the persona before rendering; the first allow only binds.
  - Green: `end_visitor_session(state=None)` and `_bind_account(identity, state)` in `auth_gate`; the Sign out handler.
- [x] **Step 12 — Existing suite through the gate (US4.8; AC4.8.1, AC4.8.2; NFR3.11).** Switch the `app` fixture in `test_dashboard_app.py`, `_run_app` in `test_dashboard_data.py` and `_render` in `test_dashboard_embedded.py` to `gate_app`. Update the assertions that read the old caption ("Logged in as" becomes "Acting as"). All pre-existing dashboard tests pass, and the count is at or above the Step 1 baseline.
- [x] **Step 13 — No I/O, no waiting, timing (NFR2.11, NFR2.12, NFR2.13; P1–P3).**
  - Red/Green:
    - socket `connect` and `create_connection` patched to record and raise during one allowed run (start stubbed) and three refused runs; none is recorded;
    - an AST scan of `auth_gate.py` and `secrets_bridge.py` finds no `sleep` call, no `while`, and no `for` loop containing `try`;
    - a `perf`-marked test runs the gate 50 times with a 50-entry allowlist and asserts p95 at most 50 ms. It is skipped by default and never run in CI.
- [x] **Step 14 — Secrets example and docs (US10.1 U3 share; AC10.1.3; BR4.5; D9).**
  - Red: a test parses `.streamlit/secrets.toml.example` with `tomllib` (3.11+, skipped on 3.10) or a line scan. It asserts no `HSM_SIGNING_SECRET` key is set, the five auth keys and `HSM_ALLOWED_EMAILS` are present, and every value is an angle-bracket placeholder or the Google discovery URL. A second test asserts `.gitignore` still ignores `.streamlit/secrets.toml` and not the example.
  - Green: `.streamlit/secrets.toml.example`.
  - Docs:
    - `CLAUDE.md`: the dashboard reads `.env.local` itself, so drop the export instruction; describe the sign-in gate and the secrets example.
    - `dashboard/README.md`: sign-in, the local run with the example, and the identity seam for tests.
    - `README.md`: the dashboard command.
- [x] **Step 15 — Verification and traceability.**
  - Run the unit commands in `unit-test-instructions.md`, then the full suite `python3 -m pytest tests/ -q`, `ruff check .`, `ruff format --check .`, and `coverage run -m pytest tests/ -q && coverage combine -q && coverage report`.
  - The test count stays at or above `.test-floor` and coverage at or above `.coverage-floor`. Neither floor file is edited.
  - Start the dashboard locally (`scripts/dev-secret.sh` if needed, copy the example, `streamlit run dashboard/app.py`). Confirm Screen 1 shows over HTTP on 127.0.0.1 with a request check, then stop it. This is the local half of the walking-skeleton slice.

## Commits

After generation, the human is asked before the commit. There is one commit through `/commit` on `dashboard-hosting`, "Put a Google sign-in gate in front of the dashboard", with its tests and both locks. Pushing and the draft pull request also wait for the human's go-ahead. The intent ships as one pull request (team.md Way of Working).

## Story Traceability

| Story | Steps |
|-------|-------|
| US8.1 New packages through the locks | 2 |
| US4.5 Decision is a pure, tested function | 4 |
| US2.5 Hosted secrets reach the app | 6, 7, 14 |
| US4.4 Gate fails closed | 7, 9 |
| US4.1 Nothing shows before sign-in | 9 |
| US4.2 Allowed visitor gets in with Google | 4, 9 |
| US4.3 Refused visitor sees a neutral refusal | 9 |
| US4.6 Signed-in block in the sidebar | 10, 11 |
| US4.7 Refusals logged without the email | 8 |
| US4.8 Existing dashboard tests run through the gate | 3, 12 |
| US10.1 Docs (U3 share) | 14 |

## Assumptions & Open Questions

- The real Google `email_verified` type is confirmed only by a real local sign-in with a local OAuth client (security-design residual risk). That needs the human's own Google client, so the plan leaves it to the human after generation. Until then, `is not True` refuses every visitor, which fails closed.
- The test count of the three existing dashboard files is taken from Step 1's run, not from the earlier figure of 66.

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
