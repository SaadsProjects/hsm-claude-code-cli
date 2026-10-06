**Collaborator:** aidlc-developer-agent

## Contribution

Support review of the lead draft (`team-practices.md` § Code Style, plus the
Code Style aspects of `discovered-rules.md` and `evidence.md`). It covers naming,
layer boundaries, error handling and file organisation. Everything was checked
against the working tree at `825a0f8`. Commands were run from `.venv`:
`ruff check .` passed, and `ruff format --check .` reported "365 files already
formatted".

### 1. Naming: matches the code, no change needed

- Error classes in the code: `HsmApiError`, `SessionExpired`, `HsmUnavailable`
  (`agents/hsm_client.py:52,60,69`), `TokenError` (`mock_hsm/auth.py:55`),
  `ApiError` (`mock_hsm/server.py:38`), `AuditFailure`
  (`mock_hsm/writes.py:1040`), `AuditUnavailable` and `InvalidEntry`
  (`mock_hsm/audit.py:86,90`). Private ones carry the leading underscore
  (`_NoAnswer`, `_Unrecordable`). All of them fit "end in `Error` or name the
  condition".
- Module-level constants are UPPER_SNAKE (`HSM_BASE_URL`, `USERS`), and the
  private secret is `_SECRET`. Modules are snake_case. Nothing has drifted.

### 2. Error handling: the BLE001 rule is narrower than the code, and two lines break it

The draft carries this rule forward unchanged: "A broad `except Exception` is
allowed only at a boundary that turns the failure into visible state or an
HTTP status, and it carries a `# noqa: BLE001 -- <reason>` comment."

- **Eight of the ten `noqa: BLE001` lines give a reason**: `mock_hsm/server.py:731`,
  `mock_hsm/writes.py:1420,1508,1673,1709`, `dashboard/actions.py:132,218` and
  `dashboard/app.py:442`.
- **Two give no reason** (CQ-10): `.claude/hooks/lint_before_commit.py:372` and
  `.claude/hooks/require_no_violations.py:87`. Both are real boundaries. Each
  turns a hook crash into a `deny` or a pass-through, and the comment under
  each already explains why in prose. So the fix is one line each: move that
  prose into the `-- <reason>` suffix. Behaviour does not change.
- **Ruff cannot enforce the reason text.** `BLE001` only asks for a `noqa`.
  No rule in the pinned set checks what comes after `--`. The reason
  requirement is therefore checked by review: the `code-reviewer` subagent
  through `/commit`. CI does not check it. The rule should say so, so nobody
  assumes the `lint` job guards it.
- **A second legitimate shape exists that the rule does not describe.** Three
  broad catches log or clean up and then re-raise the exception unchanged. They
  carry no `noqa`, because ruff does not flag a re-raised exception:
  - `mock_hsm/server.py:367` and `:554`: audit the failure, then `raise`
  - `mock_hsm/audit.py:340`: `except BaseException:`, close the file
    descriptor, unlink the temp file, `raise`

  Read literally, "allowed only at a boundary" makes these violations, yet they
  are the correct pattern. I propose wording that covers both shapes:
  > A broad `except Exception` is allowed only (a) at a boundary that turns the
  > failure into visible state, a deny, or an HTTP status, with a
  > `# noqa: BLE001 -- <reason>` comment (ruff does not check the reason; review
  > does), or (b) to record or clean up and then re-raise unchanged, which needs
  > no `noqa`. Never swallow an exception silently.
- On CQ-10 (Code Style open point 3), I recommend fixing it in this intent,
  not later. The cost is two comment edits. They belong in the change that
  already edits `require_no_violations.py` for the call-time signing secret
  (CQ-1: "the hooks … also refuse to run without it"). `lint_before_commit.py`
  mints no token, so its edit rides along in the same change. Coverage does
  not move, and no formatting-only commit is needed.

### 3. `mock_hsm/auth.py` "stdlib only": tighten the wording

- Today `auth.py` imports `base64`, `hashlib`, `hmac`, `json` and `time`, plus
  `from mock_hsm import db` (`auth.py:16-22`). It imports nothing third-party.
  "Standard library only" is therefore slightly wrong as worded, because it
  also depends on the first-party `mock_hsm.db`.
- Suggested wording: "`mock_hsm/auth.py` imports only the standard library and
  `mock_hsm` itself. It never imports Streamlit or any other third-party
  package, because the MCP server (`mcp_server/hsm_tools.py:30`), the hook
  (`.claude/hooks/require_no_violations.py:55`) and the dashboard
  (`dashboard/session.py:26`) all import it."
- The same idea extends to all of `mock_hsm/`. The draft's Code Style says that
  "the mock server and client use only `http.server` and `urllib`". The
  in-process background start that CQ-4 needs should keep that property, so
  the backend never depends on Streamlit.

### 4. Layer boundaries: verified, with one refinement for this intent

- Verified: `mcp_server/` imports no `mock_hsm.db`. The dashboard imports only
  `mock_hsm.db.USERS` (`dashboard/app.py:34`) and `mock_hsm.auth.mint_token`
  (`dashboard/session.py:26`), as the draft says. `HSM_BASE_URL` is frozen at
  import (`agents/hsm_client.py:22,147`), which matters for where the backend
  is started (see section 5).
- Refinement: CI already expects `agents/build_info.py` (the `ci.yml:241`
  watch list). Build identification (commit SHA with a source-fingerprint
  fallback) is not a domain calculation, yet it will live in `agents/`. The
  layer rule should allow it without a carve-out: "`agents/` holds
  deterministic, framework-free code: the domain calculations and small pure
  helpers such as build identification. It never imports Streamlit." This
  keeps `build_info` unit-testable and usable from both the dashboard and
  `scripts/postdeploy_check.py`.

### 5. File organisation: where this intent's new code should live

CI decides some paths, and the code structure decides the rest. I propose
adding a short **[NEW]** bullet to Code Style, or a cross-reference from the
Testing Posture bullet that already lists the watch paths:

| Concern (scope item / CQ) | Path | Why |
|---|---|---|
| Sign-in gate (`st.login`, verified email, allowlist) | `dashboard/auth_gate.py` | Fixed by the `browser-tests` watch list (CQ-8). Streamlit code belongs in `dashboard/`. |
| Stable markers the browser check asserts on | `dashboard/markers.py` | Fixed by the watch list. |
| Build identifier | `agents/build_info.py` | Fixed by the watch list. Pure and framework-free (section 4). |
| Post-deploy check | `scripts/postdeploy_check.py` | Fixed by the watch list. |
| Browser tests | `tests/test_*browser*.py` | Must match `tests/.*browser.*`, or the required check no-ops. Non-browser unit tests of the same logic go in ordinary files (for example `tests/test_postdeploy_check.py`), so they run in the `tests (…)` jobs and count toward `.test-floor`. |
| Streamlit secrets → environment bridge | `dashboard/` (for example inside `auth_gate.py`, or its own module) | Required by the `project.md` Code Style rule. Must run before `agents.hsm_client` and `mock_hsm.auth` read the environment. |
| Single in-process backend start (CQ-4) | an imported, stdlib-only `mock_hsm/` function (for example a background start next to `run()` in `server.py`) | `app.py` re-runs on every interaction, so a guard there cannot hold. A module cached in `sys.modules` can. Keeping it in `mock_hsm/` keeps the backend free of Streamlit. |
| Call-time secret read (CQ-1) | `mock_hsm/auth.py` | Replaces the module-level `_SECRET` (`auth.py:24`) together with the literal and its `TEMPORARY_EXCLUSIONS` entry (CQ-2 / M1). |

Two coverage consequences belong in the same note:

- `.coveragerc` measures `agents`, `dashboard`, `mock_hsm`, `mcp_server` and
  `.claude/hooks`, but **not `scripts/`**. So `scripts/postdeploy_check.py`
  does not count toward the 95.00 floor. Its quality bar is the Testing
  Posture rule instead: the happy path plus at least two error cases.
- Code that only runs under `-m browser`, such as the Streamlit-bound parts of
  `auth_gate.py`, is not exercised in the coverage run. That run executes on
  3.14 with browser tests skipped. Keep the allowlist and email-verification
  decisions in plain functions that ordinary tests can call, with the
  `st.login` / `st.user` calls kept thin. Otherwise the new dashboard modules
  lower measured coverage against the 95.00 floor.

### 6. Other Code Style points in the draft

- **Formatter [CHANGE]**: confirmed. The tree is formatted (365 files), and the
  required `lint` job runs `ruff format --check`. Past tense is correct.
- **Dependencies [NEW]**: matches `CLAUDE.md` § Continuous integration.
  Authlib (through `streamlit[auth]`) belongs in `requirements.in`, because
  `st.login` needs it at runtime on the hosted app. `playwright` belongs in
  `requirements-dev.in`. Agreed.
- **Security-exception register [NEW]**: matches the standing `project.md`
  correction on `filter_audit.py` / `filter_bandit.py`. Agreed. A short
  pointer would avoid restating it.
- **Candidate F2** (never commit `.streamlit/secrets.toml` or `.env.local`):
  supported from the code side. `.gitignore` does not cover
  `.streamlit/secrets.toml` at all, and covers `.env.local` only through
  `*.local` inside the block that `aidlc config --force` rewrites.

## Positions

- AGREE: Naming rules carried forward unchanged. Every error class and constant in `agents/` and `mock_hsm/` already conforms.
- AGREE: Formatter [CHANGE] to past tense. `ruff format --check .` is clean, and the required `lint` job enforces it.
- AGREE: Dependencies [NEW] (edit `.in` only, recompile both locks together, Authlib runtime, playwright dev). This matches `CLAUDE.md` and the `lock-check` job.
- AGREE: Security-exception register [NEW]. It restates an existing `project.md` correction, so a cross-reference is enough.
- AGREE: Layer boundaries as drafted, including `mock_hsm/auth.py` staying free of Streamlit. Imports verified at `dashboard/app.py:34`, `dashboard/session.py:26`, `mcp_server/hsm_tools.py:30`.
- OBJECT: The `# noqa: BLE001 -- <reason>` rule carried forward unchanged. It omits the record-and-re-raise shape used correctly at `mock_hsm/server.py:367,554` and `mock_hsm/audit.py:340`, and it implies ruff enforces the reason when only review does. Adopt the two-shape wording in section 2.
- OBJECT: Wording "`mock_hsm/auth.py` stays standard-library only". It also imports first-party `mock_hsm.db`. Say "standard library and `mock_hsm` only, never Streamlit or another third-party package".
- AGREE: Fix CQ-10 in this intent (Code Style open point 3), as a two-line reason edit inside the change that already touches `require_no_violations.py` for CQ-1.
- AGREE: CI's watch paths decide where browser-related modules go (Testing Posture [NEW]). I also propose a Code Style file-placement note (section 5) covering the secrets bridge in `dashboard/` and the single-instance backend start in a stdlib-only `mock_hsm/` module.
- AGREE: Candidate F2 (never commit `.streamlit/secrets.toml` / `.env.local`). The `.gitignore` gaps are real, and one lies inside the AI-DLC-managed block.
- AGREE: Candidate M1 (remove the burned literal and its exclusion in one commit). `scripts/check_burned_secret.py` makes any other order fail.
