# Reliability Requirements — Dashboard Deployment Pipeline

## Sources

- `requirements.md` NFR3 (coverage), NFR4 (regression baseline), NFR6 (best-effort reliability), FR6 to FR8 [requirements]
- NFR questions NQ2 (build SHA), NQ3 (headless check), NQ6 (coverage switch-on), NQ8 (reset banner), NQ11 and NQ13 (scheduled check)

## Availability stance

There is **no availability target (SLO/SLA)** for staging or production [requirements Q8]. The demo is best effort. The SLO-style numbers below are deploy-correctness criteria, not uptime commitments.

## Requirements

| ID | Requirement | Verify |
|---|---|---|
| **NFR6.1** | Each app shows a **build identifier** on the sign-in page, visible without signing in. **Primary:** the 40-character commit SHA from `git rev-parse HEAD` in the app's checkout. **Fallback, if `.git` is absent on Streamlit Cloud:** a *source fingerprint*. This is the SHA-256 over the sorted list of tracked application files (`agents/`, `dashboard/`, `mock_hsm/`, `requirements.txt`), each path followed by its bytes. One shared function computes it, and the post-deploy check computes the same fingerprint from the commit under test. The identifier carries its kind (`sha:` or `fp:`). If neither can be computed, the app shows `unknown`, and every check treats `unknown` as a mismatch [NQ2, review R-03]. | Unit tests: the resolver returns `sha:<40 hex>` in a git checkout and `fp:<64 hex>` without `.git`. The fingerprint is identical when computed by the app helper and by the check script over the same tree, and it changes when any covered file changes. |
| **NFR6.2** | **Post-deploy check pass criteria.** All steps run in **one Playwright session** with a fresh browser context and no cookies, because the page renders over a websocket and plain HTTP can't read it [NQ2, NQ3, review R-03]. (0) **Wake:** if Streamlit Cloud's hibernation page is shown, click its wake-up button once (NFR6.3), then continue. (a) Reload every 15 s, for at most 10 min, until the rendered build identifier equals the one expected for the commit under test. (b) Then `GET /_stcore/health` returns HTTP 200 with body `ok`, subject to NFR6.7. (c) Within 15 s of the final load: the sign-in button is visible, the demo banner (NFR6.11) is visible, and no text from the data-marker list (security NFR1.15) appears anywhere on the page. The failure message names the first step that failed. | Script tests (requirements FR8.4): happy path; a hibernated app that wakes; the identifier never matches before the timeout; a data marker visible to an anonymous visitor. |
| **NFR6.3** | The check is read-only. It never signs in, fills or submits a form, writes data, or calls `publish_schedule` or `submit_purchase_order` [hard rule]. Its **only** permitted click is one click on Streamlit Cloud's hibernation wake-up button, located by that button's own text. This is a platform control, not an app action [review R-02]. | A static test over the check script asserts it contains no `fill`/`type`/`check`/form submission and exactly one `click` call, whose selector is the wake-button constant. Code review. |
| **NFR6.7** | `/_stcore/health` may not be reachable through Streamlit Cloud's front end. Step (b) is therefore **mandatory when the endpoint answers and skipped with a logged notice when it returns 404 or is redirected to the platform page**. Steps (0), (a) and (c) are always mandatory. The behaviour observed on Cloud is recorded in the runbook at the skeleton checkpoint. | Script tests: a 200 `ok` passes (b); a 404 skips (b) with a notice; a 500 or a timeout fails (b). |
| **NFR4.1** | Regression baseline: on both matrix legs, the suite passes with **at least 745** passing tests, 0 failures, and `perf` tests deselected. A test may be retried **once** (`pytest-rerunfailures`, `--reruns 1`). A test that fails its retry fails the run. Every rerun is listed in the job summary [requirements NFR4]. | CI result. The job summary lists rerun tests. |
| **NFR3.1** | **Coverage switch-on** [NQ6]: the first pipeline PR measures line coverage over the package set (requirements FR1.3). If it is **≥ 80%**, `--fail-under=80` is enabled in that PR. If it is **< 80%**, a ratchet gate fails any PR whose total coverage is below the value in a checked-in file, `.coverage-floor` (one number, two decimals). A PR may only raise that number, and CI fails a diff that lowers it. The promotion workflow refuses to run until `.coverage-floor` is ≥ 80.00 and the 80% gate is on. The floor and the measured set are never lowered [review R-09]. | Coverage job. Unit tests for the ratchet comparator (below floor fails; equal passes; a lowered `.coverage-floor` in the diff fails). The promotion workflow's precondition check (unit-tested). |
| **NFR6.10** | **Rollback:** moving `production` back to a previously promoted commit through the promotion workflow brings production to that build within the NFR6.2 window, which the post-deploy check confirms. | Exercised once at the skeleton checkpoint (promote, then roll back), with the result recorded in the runbook. |
| **NFR6.11** | **Data reset is visible:** while persistence is deferred, every page (including the sign-in page) shows the banner "Demo data — resets on every redeploy or restart" [NQ8]. | AppTest unit test: the banner text is present both signed-in and anonymous. The Playwright check asserts the banner is visible. |
| **NFR6.12** | **Recovery:** after an app restart or redeploy, the app reaches a working state (the sign-in page is served with the correct SHA) with no manual step. | Covered by NFR6.2 on every deploy. |

## Graceful degradation

| Dependency | Failure | Behaviour |
|---|---|---|
| In-process backend thread | Fails to start or dies | The app shows the existing "Can't reach the HSM backend" error with no data, and a restart recovers it (NFR6.12). |
| OIDC provider | Unavailable | Sign-in fails, and no data is shown (fail closed). |
| Secrets missing | Signing secret, allowlist or OIDC settings absent | The app fails closed with a configuration error and no data (security NFR1.2, NFR1.3). |

## Out of scope

- Persistence of data or the audit log (deferred), RTO/RPO, backups, and multi-region.

## ID note

NFR6.8 and NFR6.9 were renumbered to NFR4.1 and NFR3.1 so they sit under their correct inception parents. The numbers 6.8 and 6.9 are deliberately left unused.

## Assumptions & Open Questions

- [assumption] Streamlit Community Cloud redeploys a tracked branch within 10 minutes of a push under normal conditions.
- [assumption] Streamlit Community Cloud's hibernation page has a single wake-up button identifiable by its text. The exact text is captured as a constant at the skeleton checkpoint.
- Open: whether the Cloud checkout includes `.git` decides which build-identifier kind NFR6.1 uses. Both kinds are specified, so this changes no requirement. It is confirmed and recorded at the skeleton checkpoint.
- Open: whether `/_stcore/health` is reachable on Cloud. NFR6.7 defines the behaviour either way. It is confirmed and recorded at the skeleton checkpoint.
