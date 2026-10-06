**Collaborator:** aidlc-quality-agent

## Contribution

Quality-agent support review (blind, practices-discovery Step 3). Focus: testing posture, coverage tooling, what the pipeline's CI quality gates should run, and testing gaps the interview has to settle. Every finding below comes from evidence I inspected or re-ran myself on 2026-10-04 at `1586133`, with the working tree as given.

### 1. Measured baseline (supersedes the remembered figure)

- `pytest tests/ --collect-only` finds **757 tests**. With `-m perf`, 12 of them are selected.
- `python -m pytest tests/ -q` gives **745 passed, 12 skipped (perf), 86.7 s wall time**, using about 54% CPU, so much of the time is spent waiting on sleeps and timeouts. Environment: `.venv`, **Python 3.14.7**, pytest 9.1.1, macOS.
- `ruff check .` (ruff 0.16.8) reports **All checks passed**.
- Slowest tests: `test_hooks.py::test_hung_backend_denied_before_hook_timeout` takes 5.1 s by design. The `test_dashboard_app.py` AppTest cases take about 1 to 2 s each.
- The pipeline's first green run has to match this baseline. The CI job should set the regression rule "the existing suite stays green" against these counts.

### 2. Facts in the test harness that constrain how CI runs the suite

1. **How `perf` gets skipped.** `tests/conftest.py::pytest_collection_modifyitems` skips `perf` tests only when **no `-m` expression is given** (`if config.getoption("markexpr"): return`). Any CI `-m` filter turns that skip off, even one that has nothing to do with `perf` (for example `-m "not slow"`), and then the timing tests run. So the default CI gate must call plain `python -m pytest tests/` with no `-m`, or use `-m "not perf"`. Timing tests should run only in a separate job that does not block.
2. **Fixed ports block parallel runs.** `test_mcp_tools.py` binds `TEST_PORT = 8772` and `test_hooks.py` binds `8773`. `pytest-xdist` 3.8.0 is installed in `.venv`, but `requirements.txt` does not list it. Running `-n auto` would make workers collide on those ports. The suite should run serially in CI unless those ports are made ephemeral first. At about 87 s, it fits a 10-minute feedback budget without parallelism.
3. **One timing assertion is not marked `perf`.** `tests/test_hsm_client_writes.py:854` asserts `0.6 <= elapsed < 3` for two 0.3 s timeouts. A heavily loaded shared runner could break the 3 s ceiling. Of all the default-gate tests, this is the most likely to flake in CI. It should be watched and not quietly retried.
4. **External tools needed.** `test_lint_hook.py` shells out to `git` (`git init`/`add` in `tmp_path`) and runs the hook, which looks for ruff on `PATH`, then in `.venv/bin`, then via `python -m ruff`. CI needs `git` and `pip install -r requirements.txt`, which brings in ruff. Other tests start subprocesses with `sys.executable`: the MCP server over stdio and the hook scripts.
5. **Environment hygiene.** `agents/hsm_client.py` reads `HSM_BASE_URL` when the module is imported, and the hooks read `HSM_ACTIVE_USER`. Tests create their own servers and personas, and `conftest.py` sends every audit write to a temp file. The CI test job should **not** export `HSM_BASE_URL`, `HSM_ACTIVE_USER` or `HSM_AUDIT_PATH`, and must run the suite through pytest so the `conftest.py` fixtures load.
6. **Interpreter version.** The suite has only been run on 3.14.7. The declared floor is 3.10: `ruff.toml` sets `target-version = "py310"`, `CLAUDE.md` says "3.10+", and streamlit, mcp and pytest all require `>=3.10`. Nothing shows the code works on 3.10 to 3.13. The CI interpreter, and the Python in any deploy image, has to be a version the suite has actually passed on. Choosing between one version and a floor-plus-current matrix is an interview question (G2).
7. **Unpinned tools drift.** `ruff`, `pytest` and `streamlit>=1.64` have only lower bounds and there is no lockfile. A newer ruff can add rules to the selected groups (`RUF`, `B`, `UP`, ...), and CI would then fail with no code change. A newer streamlit can change `AppTest` behaviour. For CI to be reproducible, the gate tools should be pinned to the tested versions (ruff 0.16.8, pytest 9.1.1, streamlit 1.64.0, mcp 1.30.0) or come from a constraints file.

### 3. Coverage: what the org floor means here

- `org.md` § Testing Posture says the `infra` scope "add[s] an 80% line-coverage floor and CI execution before merge". Scope floors are additive, they "may not be weakened to make a step pass", and `team.md` can only make them stricter. So the interview cannot decide whether the floor applies. It can only decide **how it is measured**: which packages count, line or branch coverage, and how to handle code that only runs in subprocesses.
- No coverage tool exists today (`coverage`/`pytest-cov` are not in `.venv` or `requirements.txt`). I did not install one, so **the current percentage is unknown**. The first step of Construction should be a baseline measurement with no gate, before the 80% gate is switched on.
- **Measurement trap.** `mcp_server/hsm_tools.py` runs only as a stdio subprocess in `test_mcp_tools.py`. `.claude/hooks/require_no_violations.py` and `lint_before_commit.py` are mostly exercised as subprocesses in `test_hooks.py` and `test_lint_hook.py`. Plain `pytest --cov` will show them as barely covered. Coverage's subprocess measurement has to be enabled (coverage.py's subprocess patching or its start-up hook), or the measured scope has to be stated explicitly. Otherwise the floor will fail for a misleading reason, or will be met by leaving packages out without saying so.
- Suggested measured set, for the human to confirm: `agents/`, `dashboard/`, `mock_hsm/`, `mcp_server/`, plus `.claude/hooks/*.py` with subprocess measurement on. Exclude `tests/`.

### 4. Proposed CI quality gates, in order

| # | Gate | Command / check | Blocking? | Notes |
|---|---|---|---|---|
| 1 | Lint | `ruff check .` with the pinned ruff | Yes | Mirrors the local hook. Fast-fail first. |
| 2 | Unit + integration suite | `python -m pytest tests/ -q` (no `-m`) | Yes | 745 tests, about 87 s locally. Suggested job timeout 15 min. Emit JUnit XML for annotations. |
| 3 | Coverage floor | the same run under coverage, `--fail-under=80` once the baseline is known | Yes, after the baseline | §3 above. Never lowered to get a run to pass. |
| 4 | Build artefact | build the deployable artefact (image or package) at the git SHA | Yes | Its Python version must match a tested one (§2.6). |
| 5 | Artefact smoke (pre-deploy) | start backend + dashboard from the built artefact; Streamlit health endpoint returns 200; one **read-only** authenticated GET through `HsmClient` | Yes | This is the pipeline's integration test of its own config. |
| 6 | Post-deploy smoke | the same read-only checks against the deployed environment | Yes (fails the deploy, triggers rollback) | Must never call `publish_schedule`/`submit_purchase_order` or write data (lead's Forbidden candidate). |
| 7 | Perf | `python -m pytest tests/ -m perf` | **No**, advisory or manual | `conftest.py` documents that timing budgets depend on the machine. |

The pipeline config is the new code in this intent. With Test Strategy Standard, it is "tested" by gates 4 and 5 (build plus container smoke) and by a lint of the workflow YAML (for example `actionlint`, if GitHub Actions is chosen). Python unit tests are only needed for any helper scripts the intent adds, such as a smoke-check script. Each such script needs a happy path and at least two error cases (backend unreachable, health non-200), as `phases/construction.md` requires.

### 5. Walking skeleton / verification command

A candidate for the human-authorized Construction Verification Command for the skeleton: a commit on the trunk triggers the pipeline, gates 1 to 2 and 4 to 5 run, and the post-deploy read-only smoke (gate 6) succeeds in one environment. Before the deploy target is chosen, a local equivalent would be `ruff check . && python -m pytest tests/ -q` followed by the containerized smoke script. The human has to approve the exact command. I am not proposing it as decided.

### 6. Gaps the interview must settle (to be added to the lead's Q list)

- **G1.** Coverage measurement (refines Q5): which packages are measured, line or branch, subprocess measurement on or an explicit exclusion list, and whether the 80% applies to the whole repo or only to changed code. Note the org-floor constraint in §3.
- **G2.** CI Python version(s): only 3.14 (what's tested), or a 3.10 + 3.14 matrix to back the declared floor? Which version goes in the deploy image?
- **G3.** Flaky-test policy: should a failed test be retried in CI (for example `--reruns`), or should a failure always block and the test go into a quarantine list with an owner? I recommend no automatic retries and a fix-or-quarantine rule, starting with `test_hsm_client_writes.py:854`.
- **G4.** Perf tests: never run, run nightly/manual as advisory, or run on a pinned runner with budgets? (They must not block. See the candidate rule below.)
- **G5.** Pinning: pin the gate tools in `requirements.txt`, add a constraints/lock file, or float with a scheduled "latest" job?
- **G6.** Smoke-test credentials: the read-only smoke needs a persona token. In a deployed environment, where does the signing secret come from? (This overlaps Q9. It decides whether gate 6 can authenticate at all.)
- **G7.** Deployed audit trail: the backend returns 503 on gated writes when `HSM_AUDIT_PATH` is not writable. Should the post-deploy smoke assert that the audit path is writable without writing a business record? Or should that be a startup health check?

### 7. Additional candidate rules (for `discovered-rules.md`, pending human confirmation)

- NEVER make the `perf`-marked timing tests a blocking CI gate. They are machine-dependent by design. *(source: `tests/conftest.py` comment "a slow disk or busy CI runner must not fail the suite"; `CLAUDE.md` § Commands "skipped by default")*
- NEVER lower the coverage floor, or narrow the measured package set without recording it, to make a pipeline run pass. *(source: `org.md` § Testing Posture "may not be weakened to make a step pass")*
- ALWAYS run the CI suite with plain `python -m pytest tests/`, or with an explicit `-m "not perf"`, never with an unrelated `-m` expression. *(source: `tests/conftest.py::pytest_collection_modifyitems` un-skip behaviour)*

## Positions

- AGREE: Testing Posture `Methodology: test-after`, kept provisional — tests that ship in the same commit as the code fit test-after but don't prove TDD, so the draft correctly holds back from claiming it.
- AGREE: "Coverage is not measured … No CI runs the suite today" — confirmed: there is no `coverage`/`pytest-cov` in `.venv` or `requirements.txt`, and no `.github/` or other CI config.
- AGREE: candidate Mandated rule on pointing the test audit trail at a temporary file, including in CI — `conftest.py` already enforces it through autouse fixtures, as long as CI runs through pytest and does not export `HSM_AUDIT_PATH` (§2.5).
- AGREE: candidate Forbidden rule that no pipeline, smoke or deploy step calls `publish_schedule`/`submit_purchase_order` — this sets my gates 5 and 6 to read-only checks.
- AGREE: Q11 asking whether ruff becomes a blocking CI gate and whether dependencies are pinned — ruff is unpinned and there is no lockfile, so CI can turn red with no code change (§2.7).
- OBJECT: Testing Posture "The suite is about 735 tests and takes about 86 s" — this figure is stale. The re-run measurement on 2026-10-04 is 757 collected, 745 passed, 12 perf skipped, 86.7 s on Python 3.14.7. The CI regression baseline should use the measured counts.
- OBJECT: Testing Posture / Q5 frame the 80% line floor as optional ("Whether that floor applies… Should we adopt") — under `org.md` the `infra` scope floor is additive and cannot be weakened, and `team.md` can only make it stricter. Q5 should ask *how* it is measured (packages, line or branch, subprocess-run code, whole repo or changed code), not *whether* it applies. Note too that plain `pytest --cov` will under-report `mcp_server/` and `.claude/hooks/`, because they run as subprocesses.
- OBJECT: Q2 (PR versus direct push) is posed as an open preference — under the `infra` scope, `org.md` requires "CI execution before merge", and § Code Style says lint "Run in CI before merge; failure blocks the PR". If direct pushes to `main` continue with CI only after the push, that requirement is not met. The question should name the constraint, so the human picks between a required PR check (or protected `main`) and an explicit, recorded deviation.
- OBJECT: the evidence table says "`pytest-xdist` 3.8.0 is installed in `.venv` but no configuration uses it" and stops there — it should add that the fixed ports 8772 and 8773 make `-n` parallel runs unsafe, so nobody adopts xdist in CI by assuming it is just an unused speed-up (§2.2).
