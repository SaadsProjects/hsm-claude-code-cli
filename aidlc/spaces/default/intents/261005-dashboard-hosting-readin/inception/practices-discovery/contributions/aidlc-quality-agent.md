**Collaborator:** aidlc-quality-agent

## Contribution

Support contribution from the quality agent. It covers testing posture, coverage tooling, CI quality gates and test patterns. Evidence was read at commit `825a0f8`: `.github/workflows/ci.yml`, `tests/conftest.py`, `.coveragerc`, `.test-floor`, `.coverage-floor`, `scripts/test_floor.py`, `scripts/coverage_gate.py`, `requirements-dev.in`, the `tests/` layout and `codekb/hsm-claude-code-cli/code-quality-assessment.md`.

**Measurement limit.** I could not run the suite. The engine's state-transition guard blocks a delegated agent from running executables beyond inspection. So the pass count, skip count, run time and coverage at `825a0f8` are still unmeasured, as the lead's draft already says. The re-measurement should be run by the main session and should match CI. On Python 3.14 (`GATE_PYTHON`), that means `coverage run -m pytest tests/ -q --reruns 1 --junitxml=junit.xml`, then `coverage combine -q`, then `python scripts/test_floor.py junit.xml`. Record the passed, skipped and failed counts, the run time and the total coverage.

### Q1. How the floors are actually enforced (adds detail to the lead's Testing Posture)

- **Test floor is checked per matrix leg.** Each `tests (…)` job runs `scripts/test_floor.py` against its own `junit.xml`. Python 3.10, 3.14 and any `HOSTED_PYTHON` leg must each have no failures and at least `.test-floor` passing tests. The draft's wording ("the minimum number of passing tests CI accepts") is correct. It should say "in every leg of the matrix", because a version-specific skip on one leg could push that leg alone below the floor.
- **Coverage is measured on 3.14 only.** Only the `GATE_PYTHON` leg runs under `coverage`. `coverage-gate` reads that leg's `coverage.json`. So code that only runs on 3.10, or on `HOSTED_PYTHON`, is not measured. This is acceptable today, because no code branches on the Python version. It should be stated so that nobody assumes the hosted Python version is covered.
- **The 80% gate is conditional.** `scripts/coverage_gate.py` switches the 80% gate on only when the floor is at least 80. At 95.00 it is on, so the draft's "two limits" is correct today.
- **Ratchet at the end of this intent.** `project.md` records that the first floors were set with headroom (745 against 811 passing, 95.00 against 96%). With 837 tests collected now, the gap has grown. Proposed practice: Build and Test re-measures and raises both floor files, keeping the same kind of headroom, in the intent's final pull request. Otherwise up to about 90 tests could be deleted without CI noticing.

### Q2. Signing secret in tests (lead's Testing Posture open point 1)

I support CQ-1's approach and add three test requirements:

1. **Set the secret before anything can read it.** `tests/conftest.py` should set a throwaway random `HSM_SIGNING_SECRET` in `os.environ`, at import time or in the existing session-scoped autouse fixture, before any module-scoped server fixture starts. Subprocess tests (`test_hooks.py`, `test_mcp_tools.py`, the lint hook) inherit it through the environment. CI still exports no HSM variables of its own.
2. **Make the hooks fail closed explicitly.** `CLAUDE.md` says a crashed or timed-out hook fails open. If `require_no_violations.py` raises because the secret is missing, `publish_schedule` would therefore be allowed. The hook must catch the missing-secret case and return an explicit deny. TDD must start with a failing test in `test_hooks.py`: run with the secret unset, and expect a deny rather than `{}` or a crash. This is the highest-risk new behaviour in the intent from a gating point of view.
3. **Regression tests for removing the burned literal.** Add the following:
   - `check_burned_secret.py` passes once the exclusion is gone (`test_ci_burned_secret.py`).
   - `mint_token` and `verify_token` raise a clear error when the secret is missing in hosted mode.
   - A token minted with one secret does not verify under another.
   - Changing the variable between calls takes effect, which proves the secret is read at call time.

### Q3. Making the sign-in gate testable (TDD for the new work)

`st.login` performs an OIDC redirect, and neither `AppTest` nor a unit test can complete it. To keep the gate testable and keep `dashboard/` above the 95.00 floor:

- **Make the decision a pure function.** Write the allow or refuse decision as a pure function, for example in `dashboard/auth_gate.py`. It takes the identity fields (signed in, email, email verified) and the allowlist, and returns allow, a refusal reason, or "show sign-in". Unit-test it with no Streamlit involved.
- **Minimum cases, each written as a failing test first:**
  - not signed in
  - signed in but the email is not verified
  - verified but not on the allowlist
  - on the allowlist, with case and whitespace normalised
  - an empty or missing allowlist, which denies everyone (fail closed)
  - a malformed allowlist in secrets, which also fails closed
  - every refusal screen still offers Sign out or reload (`project.md` correction, 2026-10-05)
- **Test the wiring with `AppTest`.** `tests/test_dashboard_app.py` already uses `AppTest`. Test the wiring by injecting a fake identity through a small seam in the module, not by reaching into Streamlit internals. Then assert that no tab and no persona picker renders before the gate allows.
- **Keep the Streamlit bridge thin.** The code that copies secrets into the environment and calls `st.login` is the only code left untested in-process, so it should be small. Do not exclude it with `# pragma: no cover` or a `.coveragerc` omit. Either one narrows the measured set, which the standing Forbidden rule forbids.
- **Leave the real sign-in to the browser layer.** The real `st.login` refusal path is covered by the browser layer only (see Q4).

### Q4. Browser tests and Playwright (lead's open points 2 and 3, and CQ-8)

1. **Remove the "no tests ran" pass.** Today `browser-tests` runs `python -m pytest tests/ -m browser -q || [ $? -eq 5 ]`. Once the first browser test exists, the `|| [ $? -eq 5 ]` must go in that same pull request. If it stays, a rename or a broken marker that deselects every browser test still passes the required check without running anything.
2. **Guard the watch list with a test.** The path watch list is a silent-failure point (CQ-8). Do not rely on people remembering it. Add a meta-test in `tests/test_ci_check_workflows.py` that checks two things:
   - every test file containing a `browser`-marked test matches the job's path regex
   - every source file those tests import from `dashboard/`, `agents/` or `scripts/` is on the list

   Then a new browser-check file that is off the list fails a normal required check.
3. **Pull requests run against a local app only.** On pull requests, browser tests run against an app started inside the job, on loopback, with the identity provider replaced by a test double (for example a fake identity through the same seam as in Q3). Staging is exercised only by the post-deploy check, never by pull-request CI, because staging is not yet the code under review.
4. **Browser tests should not count toward `.test-floor`.** They are skipped in the `tests (…)` legs, and the floor is per leg. Instead, `browser-tests` should assert a minimum of one test run whenever it runs. This follows from point 1.
5. **Pin the Chromium download.** Playwright's Chromium download sits outside the hash lock and outside `pip-audit`. From a test-reliability view, option (a) is acceptable if the browser is cached under a key that includes the pinned Playwright version, so a cache can never mix versions. Option (c), the container image, adds a Trivy obligation and slower jobs for no gain in reliability.
6. **Retry parity.** The `tests` legs use `--reruns 1`, but `browser-tests` does not. Browser tests are the most timing-sensitive tests in the suite, so the job should get the same single retry, under the same rule: a test that fails on the retry blocks the merge.

### Q5. Post-deploy check script and coverage scope

- **`scripts/` is not in the measured set.** `.coveragerc` measures `agents`, `dashboard`, `mock_hsm`, `mcp_server` and `.claude/hooks`, so `scripts/postdeploy_check.py` will not count toward coverage. The existing CI scripts are the same: they are tested through `tests/test_ci_*.py` but not measured. This matches today's practice, and the "happy path plus at least two error cases" rule still binds. Adding `scripts` to the measured set would widen it, which is allowed (only narrowing is forbidden), but it would change the coverage percentage. That is a question for the human, not something to do silently.
- **Error cases for `postdeploy_check.py`, run against a local fake server:**
  - the app does not answer, or the request times out
  - the build ID does not match the expected SHA or fingerprint
  - a visitor who is not on the allowlist is not refused (the gate is open)
  - the page loads but shows a refusal screen with no way out
- **`agents/build_info.py` is measured.** Its SHA path and its fingerprint fallback need both branches covered, including a checkout with no `.git`.

### Q6. Other test patterns the new work must follow

- **No new fixed ports.** The fixed ports 8772 and 8773 keep the suite serial (accepted). New tests that start a server (the in-process backend for the dashboard, the browser-test app) must bind port 0 and read back the port actually assigned. They must not add a third fixed port.
- **One backend per process.** Hosting adds "at most one backend per app process". Test this directly: starting the in-process backend twice in one process reuses the first instance or raises. It must not silently bind a second port.
- **Reset banner.** If Deployment open point 1 resolves to (a), the reset banner becomes a tested requirement. Add an `AppTest` assertion that the banner renders on every tab after sign-in. The existing audit behaviour (503 "audit unavailable" when the trail cannot be written) stays covered by `test_audit_routes.py`.
- **Marker hygiene.** `-m browser` switches off the default `perf` skip. A test marked both `browser` and `perf` would therefore run timing assertions in `browser-tests`. Add a case to `tests/test_conftest_markers.py` asserting that no collected test carries both marks.
- **Dependabot major bumps (`mcp` 2.x).** `test_mcp_tools.py` is one sequential scenario, so a major-version break shows up as a single opaque failure. Adding an ignore rule for majors of `mcp` and `streamlit` reduces noise from pull requests that are already known to break. Major versions are then upgraded deliberately, as their own piece of work with their own tests.

### Proposed wording for `team.md` § Testing Posture (to integrate)

- "Coverage is measured on the `GATE_PYTHON` leg (3.14). The floors are the values in `.coverage-floor` and `.test-floor`, not numbers copied into this file. The test floor applies to every leg of the matrix."
- "At the end of each intent, Build and Test re-measures and raises both floor files, keeping headroom, in the final pull request."
- "New tests that start a server bind an ephemeral port."
- "`browser-tests` fails when it runs and collects no test, once a browser test exists. A browser-check file that is off the job's path list fails a meta-test."
- "A hook or gate that cannot obtain the signing secret denies explicitly. It never relies on a crash, because a crashed hook fails open."

## Positions

- AGREE: Walking Skeleton option (a) for this intent, with the Construction Verification Command being the pull-request CI run with all 10 required checks green. A local `pytest` alone does not exercise `secrets`, `audit`, `lock-check` or the burned-secret check, so it cannot prove the slice.
- AGREE: Way of Working option (c), with the burned-secret removal as its own first pull request. Each pull request then gets the full required checks and the floor ratchet. Option (b) gives the same coverage at a higher cost.
- AGREE: The coverage [CHANGE] and test-floor [NEW] points, adding the per-leg detail and the 3.14-only measurement detail from Q1.
- OBJECT: Do not write the floor numbers (95.00, 745) or the collected count (837) into the affirmed `team.md` text. They go stale, as the baseline's 757 did. Point to the floor files instead, and keep the measured figures in `evidence.md`.
- AGREE: Re-measure the pass count, skip count and run time before Code Generation. I could not run the suite (delegated-agent guard), so this is still open.
- OBJECT: The browser-tests [NEW] bullet as drafted relies on people placing files at watched paths. It needs the meta-test, removal of the exit-5 pass once the first browser test exists, and a single retry (Q4), so that the required check cannot pass without running anything.
- AGREE: Browser tests do not count toward `.test-floor`. A minimum-one-test assertion in `browser-tests` replaces that.
- AGREE: Pull-request browser tests run only against a local app with an identity test double. Staging is reached only by the post-deploy check.
- AGREE: Signing secret in tests (Testing open point 1). Add the explicit fail-closed deny in `require_no_violations.py` and its failing test first (Q2), because a crashed hook fails open.
- AGREE: Deployment open point 4. The post-deploy check asserts that the app answers, that it shows the expected build and that it refuses a visitor who is not allowlisted. It never signs in. F1 should be affirmed.
- AGREE: Deployment open point 1 (a), the reset banner, provided the banner becomes a tested requirement.
- AGREE: Chromium option (a), with a cache keyed to the Playwright version. Option (c) adds the Trivy obligation for no gain in reliability.
- AGREE: An ignore rule for Dependabot major versions of `mcp` and `streamlit`.
- AGREE: M1, M2 and F2. M1 should also name the regression tests in Q2 point 3.
- AGREE: The standing rule note on `-m browser`, with the marker-hygiene test from Q6 to keep it true.
- AGREE: CQ-10, fixing the two `noqa: BLE001` comments that have no reason. It is a one-line lint cleanup with no effect on tests, so it fits this intent.
