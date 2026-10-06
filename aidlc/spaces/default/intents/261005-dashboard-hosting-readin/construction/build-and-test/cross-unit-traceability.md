# Cross-Unit Traceability — Dashboard Hosting Readiness

## Sources

- `inception/requirements-analysis/requirements.md`: FR1.1–FR10.1 (46 IDs) and NFR1–NFR7 (7 IDs)
- `inception/user-stories/stories.md`: 91 acceptance criteria, AC1.1.1–AC10.1.3
- Per-unit `construction/<unit>/code-generation/traceability.json` for the six units (there is no stage-level file)
- Closure evidence: `test-results.md`, `construction/staging-app/code-generation/code-summary.md` § Staging Evidence, commit `27e748e` (PR #6)

## Verdict

**FAIL under the strict rule** (each ID needs an `OK` entry in a unit traceability file whose target exists). 57 of 144 IDs have none.

- **Acceptance criteria:** 82 of 91 are `OK`. Of the 9 that aren't, 7 now have closure evidence the unit files predate, 1 is a legitimate `N/A`, and 1 is genuinely open.
- **Requirement parents (FR1.1–FR8.7, NFR1, NFR3–NFR7):** these have no unit entries, because the unit traceability files cite story ACs and the detailed NFRx.y IDs instead. Each is covered indirectly through its story group (US*n* traces FR*n*, as the story headings state), and every AC in those groups is `OK` or has closure evidence. The exceptions are listed under Genuinely Open.
- **Changing the unit files now** would invalidate the six Code Generation reviews, which have no review passes left. So the gaps are surfaced here, not patched.

### Genuinely Open

| ID | Why | Owner |
|----|-----|-------|
| NFR2 (30 s cold start) | Needs the hosted app measured from asleep; an awake run took 8.5 s | performance-validation (scheduled) |
| FR8.7 / AC8.4.1 | `.claude/hooks/lint_before_commit.py:372` still has a bare `# noqa: BLE001`. Harness files are protected from agent edits | The human, by hand (decision of 2026-10-05) |

## Acceptance Criteria Not `OK` in Unit Files

| ID | Unit status | Unit | Closure evidence now | Effective |
|----|-------------|------|----------------------|-----------|
| AC1.3.3 | Deferred | secret-fail-closed | Commit `27e748e` (PR #6) changes `mock_hsm/auth.py`, sets `TEMPORARY_EXCLUSIONS = ()` in `scripts/check_burned_secret.py`, and adds `tests/test_signing_secret.py`, all in one commit | Met |
| AC3.3.2 | Deferred | embedded-backend | The Sign out half is verified by U3's `tests/test_dashboard_gate.py`; the no-detail half by `tests/test_dashboard_embedded.py` | Met |
| AC4.8.2 | Deferred | sign-in-gate | 1195 passed against `.test-floor` 745; `tests (3.10)` and `tests (3.14)` green on PR #7 | Met |
| AC7.4.2 | Deferred | postdeploy-check | The `postdeploy` workflow (run 37464999295) and the by-hand check against staging both PASS with the same three lines | Met |
| AC8.3.4 | N/A | postdeploy-check | No required job was renamed, added or removed (M2) | N/A |
| AC8.4.1 | Deferred | secret-fail-closed | `require_no_violations.py` has its reason; `lint_before_commit.py:372` does not | **Open** |
| AC9.1.1 | none (U6 cites FR9.x) | staging-app | App created on `main` with its own secrets (owner, 2026-10-06); the gate admitted a real sign-in, so the signing and cookie secrets differ | Met |
| AC9.1.2 | none (U6 cites FR9.x) | staging-app | Check exit 0 against `https://hsm-stg.streamlit.app`; the owner saw `Build 23396d7` = `main` | Met |

## Requirement Coverage

| ID | Strict | Indirect coverage (story group, owning unit, target) | Effective |
|----|--------|------------------------------------------------------|-----------|
| FR1.1–FR1.5 | uncovered | US1.1–US1.4: all ACs OK or Met; U1; `mock_hsm/auth.py`, `tests/test_signing_secret.py` | Met |
| FR2.1–FR2.6 | uncovered | US2.1–US2.6; U1 (US2.1–2.4, 2.6) and U3 (US2.5); `scripts/dev-secret.sh`, `dashboard/secrets_bridge.py`, `tests/test_secret_entry_points.py` | Met |
| FR3.1–FR3.5 | uncovered | US3.1–US3.4; U2; `mock_hsm/embedded.py`, `tests/test_embedded_backend.py` | Met |
| FR4.1–FR4.10 | uncovered | US4.1–US4.8; U3; `dashboard/auth_gate.py`, `tests/test_dashboard_gate.py`, `tests/test_auth_gate.py` | Met |
| FR5.1–FR5.2 | uncovered | US5.1–US5.2; U4; `agents/build_info.py`, `tests/test_build_info.py` | Met |
| FR6.1–FR6.2 | uncovered | US6.1; U4; `tests/test_dashboard_build_banner.py` | Met |
| FR7.1–FR7.5 | uncovered | US7.1–US7.4 (Q6 narrowed FR7.1/FR7.2: no build assertion); U5; `scripts/postdeploy_check.py`, `.github/workflows/postdeploy.yml` | Met |
| FR8.1–FR8.6 | uncovered | US8.1–US8.3; U3 (locks) and U5 (CI); `requirements.txt`, `requirements-dev.txt`, `.github/workflows/ci.yml`, `tests/test_ci_browser_watch.py` | Met |
| FR8.7 | uncovered | US8.4: AC8.4.1 half met | **Open** |
| FR9.1, FR9.2, FR9.3 | OK | U6; `docs/staging-app.md`, `tests/test_staging_runbook.py`, `scripts/postdeploy_check.py` | Met |
| FR10.1 | OK | U6 and U1 (AC10.1.1–AC10.1.3); `docs/staging-app.md`, `CLAUDE.md`, `README.md`, `dashboard/README.md` | Met |
| NFR1 | uncovered | NFR1.1–NFR1.14 and NFR1.21–NFR1.28 all OK in U1–U3 | Met |
| NFR2 | Deferred | NFR2.1–NFR2.5 and NFR2.11–NFR2.13 OK; the 30 s whole-app figure is pending | **Open**, owned by performance-validation |
| NFR3 | uncovered | NFR3.1–NFR3.11; suite green on both legs; floors raised in the follow-up PR | Met |
| NFR4 | uncovered | NFR4.1–NFR4.4, NFR4.11 OK | Met |
| NFR5 | uncovered | NFR5.1, NFR5.11 OK | Met |
| NFR6 | uncovered | AC7.3.1 OK: the check's AST scan finds no input, sign-in, publish or PO call | Met |
| NFR7 | uncovered | NFR7.1, NFR7.2, NFR7.11 OK; `audit` and `lock-check` green | Met |

The other 82 acceptance criteria are `OK` in their unit's traceability file, with existing targets (per-unit lists in each `construction/<unit>/code-generation/traceability.json`).
