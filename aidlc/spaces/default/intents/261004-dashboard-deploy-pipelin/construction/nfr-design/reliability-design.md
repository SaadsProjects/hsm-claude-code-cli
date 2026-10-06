# Reliability Design — Dashboard Deployment Pipeline

## Sources

- `construction/nfr-requirements/reliability-requirements.md`: NFR3.1, NFR4.1, NFR6.1 to NFR6.3, NFR6.7, NFR6.10 to NFR6.12 [reliability-requirements]
- `construction/nfr-design/security-design.md`: SD5 (controls), SD6 (build identifier)
- NFR Design answers DQ1 (commit status), DQ2 (default target), DQ3 (`prod-*` tags) and DQ6 (issue on failure)

## RD1 — Post-deploy check (`scripts/postdeploy_check.py`)

**Inputs:**
- `--url`
- `--commit <40-hex>` and `--checkout <dir>`: a checkout of that commit. From these the script computes both acceptable identifiers with `agents/build_info.py`: `sha:<commit>` and `fp:<fingerprint of the checkout>`. The observed identifier must equal the expected one **of the same kind**. `unknown` never matches (review R-09).
- `--timeout 600`, `--interval 15`
- `--report <path>` for the job summary

**Flow:** one Playwright Chromium session with a fresh context and no storage state.

**Frame awareness (review R-03):** Streamlit Community Cloud serves the app inside an iframe on its own wrapper page. The app frame is the frame containing an element with the build-identifier text pattern `Build: (sha:[0-9a-f]{40}|fp:[0-9a-f]{64}|unknown)`, or the main frame when there is no iframe. Steps a and c query that frame. The data-marker scan in step c runs over **every** frame of the page (`page.frames`), so data shown in any frame fails the check.

```
goto(url)
if wake button (text == WAKE_BUTTON_TEXT) visible in any frame: click once; wake_clicked=True   # step 0
loop to deadline: find app frame; read "Build: ..." text; if same-kind match: break; reload    # step a
GET {url}/_stcore/health → 200 'ok' pass | 404/redirect → skip+notice | else fail              # step b
in app frame: sign-in button + banner visible; in ALL frames: no DATA_MARKERS text (15 s)      # step c
```

**How the identifier is emitted:** the gate (security SD1, step 1) renders it as plain text, `st.caption(f"Build: {identifier}")`. The check locates it by the text pattern above, not by a DOM attribute, because Streamlit does not let app code set `data-testid`.

- `WAKE_BUTTON_TEXT` and `DATA_MARKERS` are constants in `dashboard/markers.py`. `DATA_MARKERS` is shared with the AppTest unit tests (security NFR1.15). `WAKE_BUTTON_TEXT` is filled from the live hibernation page at the skeleton checkpoint.
- **Read-only enforcement:** the script calls `click` exactly once, with the wake-button locator, and never calls `fill`, `type`, `check`, `press` or `set_input_files`. `tests/test_postdeploy_check_static.py` asserts this over the script's AST.
- **Exit codes:** 0 pass. 1 identifier timeout (step a). 2 health failure (step b). 3 sign-in or banner missing, or data visible (step c). 4 browser or launch error. The failure message names the step.
- **Tests:**
  - happy path, against a local Streamlit app started by the test with a fake gate;
  - the identifier never matches, so the script exits 1;
  - a data marker is shown to an anonymous visitor, so it exits 3;
  - hibernation page, simulated with a static HTML fixture whose button leads to the app, so the script passes with `wake_clicked`;
  - health 404 skips with a notice; health 500 exits 2;
  - **positive controls for frames (review R-03):** a wrapper HTML fixture embeds the test app in an iframe. When the embedded app shows the sign-in page, the check passes. When the embedded app shows a data marker, the check exits 3. This proves the check sees inside the iframe.

These are integration tests marked `browser`. They run in `staging-check.yml`'s test job and in a nightly CI job, not in the default PR suite (TS11). The AST static test runs in the default suite.

## RD2 — Staging evidence (DQ1)

`staging-check.yml` triggers on `push` to `main`. It checks out `github.sha` and runs RD1 against the staging URL with `--commit ${{ github.sha }} --checkout .`. Permissions: `contents: read`, `statuses: write`. It then posts the commit status `staging-check`: `success` or `failure`, with a description naming the step that failed and a `target_url` pointing to the run. Superseded runs are cancelled (`concurrency: staging-check`, `cancel-in-progress: true`), so only the newest `main` commit's result matters for the wait.

## RD3 — Promotion and rollback (DQ2, DQ3)

`promote.yml` (`workflow_dispatch`) has two inputs: `commit` (optional) and `mode` (`promote` | `rollback`, default `promote`). It runs as **three jobs**, because GitHub holds an environment-bound job for approval before any of its steps run (review R-01).

**Job 1 `preflight`.** No environment, so no deploy key is available. Permissions: `contents: read`, `statuses: read`, `checks: read` (review R-02).
1. Guard: `github.ref == refs/heads/main`.
2. **Resolve the target.**
   - In `promote` mode with no `commit`, walk `main` from newest to oldest, at most 50 commits. Pick the first commit where every required CI check run is `success` and the `staging-check` commit status is `success`. Check runs are read with `checks: read`; statuses with `statuses: read`.
   - In `promote` mode with a `commit`, require it to be an ancestor of `main` and to pass the same checks.
   - In `rollback` mode, `commit` is required and must carry a `prod-*` tag.
3. **Coverage gate (NFR3.1):** read `.coverage-floor` at the target commit. Refuse if it is below 80.00.
4. Read the current `production` SHA. Write the target, mode, current production SHA and the precondition results to the job summary, so the approver sees exactly what is being approved. Export `target` and `prev` as job outputs.

**Job 2 `deploy`** (`needs: preflight`, `environment: production`). Permissions: `contents: read`. It **pauses for the owner's approval before any step runs**. Once approved, its only steps are:

5. The same ref guard again.
6. Load `PROD_DEPLOY_KEY` into an SSH agent. `git push --force-with-lease=production:<prev> origin <target>:production`. The lease refuses if `production` moved after preflight. Rollback is the only path whose move is not a fast-forward.
7. Create and push the annotated tag `prod-<UTC yyyymmddThhmmssZ>` on the target, recording the mode, the actor and the run URL. The deploy key is used only in this job.

**Job 3 `verify`** (`needs: deploy`, no environment, `contents: read`).

8. Check out the target and run RD1 against the production URL with `--commit <target> --checkout .`. If the check fails, the run fails. The tag stays, because the commit did reach production; the failure is visible and you decide whether to roll back.

Each precondition in steps 2 and 3 is a small Python function in `scripts/promote_preconditions.py`, unit-tested with fake GitHub API responses: all green; staging failure; CI failure; not on `main`; rollback target without a tag; floor below 80.

## RD4 — Scheduled production check (NFR7.3, DQ6)

`prod-check.yml` runs on `schedule: '17 */6 * * *'` (off the hour) and on `workflow_dispatch`. Job 1 (`contents: read`) checks out the head of the `production` branch and runs RD1 against production with `--commit <that sha> --checkout .`. Job 2 runs only `if: failure()` and has `issues: write`. It opens an issue titled `Production check failing` with the label `prod-check-failure`, or comments on the open issue that has that label, linking the run. It never closes issues automatically.

## RD5 — Backend start and recovery (NFR6.5, NFR6.12)

`dashboard/backend_runtime.py` provides `ensure_backend()`, decorated with `@st.cache_resource`, so it runs once per process.

1. Set `HSM_AUDIT_PATH` to a file in `tempfile.gettempdir()` if it is unset. The audit trail is ephemeral, which matches the deferred-persistence gap.
2. Call `serve_in_thread(host, port)` (security SD4). Like `run()`, it calls `audit.configure()` before serving, so publish and PO routes don't return 503 "audit unavailable" (review R-07).
3. Poll `GET /healthz` for up to 5 s.
4. Return the server.

If the health poll fails, `ensure_backend` raises. The app shows the existing "Can't reach the HSM backend" error and stops. Because `cache_resource` does not cache exceptions, the next interaction retries.

When `HSM_BASE_URL` points somewhere other than the in-process host and port (local development against a separately started mock), `ensure_backend` does nothing. `HSM_INPROCESS_BACKEND=1` turns it on, and Cloud sets that in secrets through the bridge. Locally it defaults to off, so current workflows are unchanged.

## RD6 — CI resilience (NFR4.1, NFR3.1)

- **Retry:** `pytest --reruns 1` retries any failing test once, as the team practice allows. `pytest-rerunfailures` records reruns in the JUnit XML, and the summary helper lists every rerun test by name, so flakiness stays visible.
- **Passing-test floor (NFR4.1, review R-04):** `scripts/test_floor.py` reads each leg's JUnit XML. It fails the job if failures plus errors exceed 0, or if passed tests fall below the number in a checked-in `.test-floor` file (initially `745`). The same "may only rise" diff check as `.coverage-floor` applies, so deleting tests can't silently lower the floor. Unit-tested with JUnit fixtures: at the floor (pass), below it (fail), a failure present (fail), and a lowered `.test-floor` in the diff (fail).
- **Coverage ratchet:** `scripts/coverage_gate.py` reads total coverage from `coverage json`.
  - It fails if the total is below `.coverage-floor`.
  - When the floor is ≥ 80.00, it also applies `--fail-under=80`.
  - A separate check fails a PR whose diff lowers `.coverage-floor`.
  - Raising the floor is a manual, deliberate edit.

## Assumptions & Open Questions

- [assumption] The Streamlit Cloud hibernation page is plain HTML with one button. Its exact text is captured into `WAKE_BUTTON_TEXT` at the skeleton checkpoint.
- None.
