**Collaborator:** aidlc-devsecops-agent

## Contribution

Blind support review, Step 3, brownfield re-run at commit `825a0f8`. Scope: lint
and format rules, SAST, secret scanning and secret handling, dependency
scanning, and supply-chain controls. Everything below was checked against the
files in the repository unless it is marked **unverified**.

### 1. What the security gates enforce today (confirms the lead's draft)

- **Lint and format**: the `lint` job runs `ruff check .` and
  `ruff format --check .` with ruff `0.16.8` from the hash-pinned dev lock. The
  local hook uses the same pin. The lead's [CHANGE] that the formatter is now in
  place is correct.
- **SAST**: the `sast` job runs `bandit -q --ignore-nosec -r agents dashboard
  mcp_server mock_hsm .claude/hooks scripts`, and `scripts/filter_bandit.py`
  blocks on HIGH severity and on files bandit could not scan. New modules under
  those paths are covered automatically. This includes the planned
  `dashboard/auth_gate.py` and the in-process backend start. `tests/` is not
  scanned, which is acceptable.
- **Secret scanning**: the `secrets` job runs gitleaks `8.30.1` (download
  checksum-verified) over full history (`fetch-depth: 0`) with `--redact`, then
  runs `scripts/check_burned_secret.py`. `.gitleaks.toml` extends the default
  rules and allowlists exactly two values: the burned literal and its SHA-256
  digest.
- **Dependency audit**: the `audit` job validates `security-exceptions.toml`
  (`check_exceptions.py`), runs pip-audit over both locks with
  `--require-hashes`, and `filter_audit.py` blocks on HIGH/CRITICAL or CVSS 7.0
  or above. It also **fails closed** when OSV has no usable rating or a lookup
  errors. The register has no active entries.
- **Supply chain**: every `uses:` is pinned by 40-character SHA with a version
  comment. `scripts/check_workflows.py` enforces this, plus top-level
  `permissions`, plus no `${{ secrets.* }}` on a `run:` line. The workflow has
  `permissions: {}` at the top and `contents: read` per job. It triggers on
  `pull_request` (not `pull_request_target`), so pull requests from forks and
  Dependabot get a read-only token. `lock-check` recompiles both locks with uv
  `0.12.15` and diffs them. Dependabot covers the Actions pins and pip weekly.

### 2. Drift: private apps or public apps with `st.login`

The lead is right that `project.md` § Deployment (learned 2026-10-04) replaced
the private-app model in `team.md`. I support aligning `team.md` with it. Moving
from "private app" to "public app, the app does its own sign-in" moves the trust
boundary from the platform into our code. The Deployment text should therefore
state the properties the gate must have, not only that it exists. Without them,
the standing Forbidden rule R-SEC-1 ("never expose … without a sign-in layer")
cannot be tested:

1. **Gate runs first and fails closed.** The identity check runs before any
   other Streamlit call renders data and before the in-process backend is
   reached. A missing or misconfigured `[auth]` section in secrets, an empty
   allowlist, or any error in the gate refuses entry. It never falls back to
   the persona picker.
2. **Verified email only.** Entry requires the identity provider's
   `email_verified` claim to be true. The address is normalised (trimmed,
   lower-cased) before the exact comparison with the allowlist. No domain
   wildcards unless the human decides otherwise.
3. **Per-environment secrets.** Staging and production each get their own
   signing secret, `[auth] cookie_secret` and OAuth client. The signing secret
   and the cookie secret are never the same value.
4. **The allowlist grants full demo power.** Inside the gate, the persona
   picker lets any allowlisted person act as any persona, including
   `SYSTEM_ADMIN`. For a demo this is acceptable, but it should be written down
   as an accepted risk, so the allowlist is understood to mean "full access".

The Walking Skeleton [CHANGE] ("visitor whose verified email is not on the
allowlist") matches this. I agree with it.

### 3. Burned-secret removal (CQ-1, CQ-2, CQ-7)

- **Atomic removal (M1)**: confirmed in the code. `scan()` reports a problem as
  soon as `mock_hsm/auth.py` is in `TEMPORARY_EXCLUSIONS` but no longer holds
  the value. The literal and the exclusion must therefore leave in the same
  commit. The two `.gitleaks.toml` allowlist entries and `PERMANENT_EXCLUSIONS`
  stay, because the value remains in git history.
- **No committed replacement secret of any kind.** After removal there must be
  no committed default, no "local dev" constant, and no fixed test secret in
  `tests/conftest.py`. Tests should generate a throwaway value per run
  (`secrets.token_urlsafe(32)`) and put it in `os.environ` early, so subprocess
  tests inherit it. I support the lead's Testing open point 1 in that form. A
  fixed string in `conftest.py` would be a new committed secret that gitleaks
  might not recognise.
- **What "local development" means needs a definition.** `team.md` says the
  app fails closed "outside local development". Once the literal is gone, no
  committed default may exist. And a random value generated per process cannot
  work, because the dashboard, the backend, the MCP server and the hooks are
  separate processes that must share one key. My recommendation: no fallback
  anywhere. Every entry point refuses to start without `HSM_SIGNING_SECRET`,
  and local developers set it from an ignored `.env.local` (or a helper script
  that writes one). The words "outside local development" would then be
  removed from the rule. This is stricter than the baseline, so it is an
  interview point, not a silent change.
- **Strength check.** The loader should refuse a secret shorter than 32 bytes,
  the HMAC-SHA256 key size. Otherwise a weak value such as `test` set in
  Streamlit secrets would pass "secret present" and still be guessable.
- **Never in committed config.** `.mcp.json` passes `env` to the MCP server
  and is committed. The secret must reach it by inheritance from the shell's
  environment, never as a value in `.mcp.json`, `.streamlit/config.toml` or
  `settings.local.json.example`. Error messages from the loader name the
  variable, never the value.

### 4. New dependencies under the gates

- **Authlib (`streamlit[auth]`)** goes into `requirements.in`, so it is in the
  runtime lock, which pip-audit covers. Authlib implements JOSE/JWT handling
  and has had advisories in that area. A future HIGH advisory will block every
  pull request, including unrelated ones. The expected response is a
  Dependabot bump or a register entry with a reason and expiry, never a
  narrower audit scope. **Unverified**: whether Streamlit Community Cloud's
  installer enforces the hashes in `requirements.txt`. pip enters hash-checking
  mode when hashes are present; I did not confirm what uv does when Cloud
  invokes it. The hosting work should check this once against a real build log.
- **Playwright** goes into `requirements-dev.in`. The Python wheel is locked and
  audited. The Chromium build downloaded by `playwright install` is not: it is
  fixed by the Playwright version but has no hash we verify. Of the lead's Code
  Style open point 1 options, I support **(a)**, with these limits written into
  the rule: Chromium is installed only in the `browser-tests` job and the
  post-deploy check, and those jobs keep `contents: read` and receive no
  secrets, deploy key or identity-provider credentials. Option (c) (a container
  image pinned by digest) is the stronger choice and brings Trivy into play,
  but its cost does not match a demo whose browser touches only our own app.
- **Browser-test watch list gap (new finding).** The `browser-tests` job runs on
  a pull request only when one of five paths changes. A Dependabot pull request
  that bumps `playwright` changes only `requirements-dev.txt`, so it would pass
  the required check without running a browser test. The nightly and push-to-
  `main` runs would catch it only after merge. Adding `requirements-dev.txt`
  and `.github/workflows/ci.yml` to the watch list closes this. The lead's rule
  that new browser-check files use the watched paths should cover this too.

### 5. Dependabot major versions (lead's Code Style open point 2)

- **`mcp`**: ignore semver-major updates. `mcp` is dev-only, it is not deployed,
  and 2.x is a known API break. pip-audit still reports any vulnerability in the
  pinned 1.x, so we do not lose sight of security fixes.
- **`streamlit`**: do **not** ignore majors. Streamlit is the internet-facing
  runtime, and its `st.login` and session-cookie handling are part of our
  security boundary. A major-version pull request that fails the screen tests
  is a useful signal. Silencing it risks being stuck on an unsupported line.
- **Unverified**: whether Dependabot alerts and security updates, GitHub secret
  scanning and push protection are switched on in the repository settings.
  `team.md` § Deployment names "GitHub push protection" as a control. It cannot
  be seen from the code, so the interview or a one-off settings check should
  confirm it.

### 6. `.gitignore` gaps (CQ-9), checked with `git check-ignore`

- `.streamlit/secrets.toml`: **not ignored**. This file is where `st.login`'s
  `[auth]` client secret and cookie secret live locally, so this is the
  highest-risk gap in this intent.
- `.env`: **not ignored**.
- `.env.local`: ignored only through `*.local` inside the AI-DLC-managed block,
  which `aidlc config --force` can rewrite.

Recommended explicit lines, outside the AI-DLC block, in the first change that
introduces any secret file: `.streamlit/secrets.toml`, `.env`, `.env.*` (with
`!.env.example` if an example is ever committed). gitleaks in CI is the second
line of defence. The ignore rule is the first, because once a secret has been
pushed to a public repository it is burned.

### 7. Smaller points

- **M3** is already covered by standing rules R-SEC-1 and R-SEC-3, because a
  public Streamlit app is exposed the moment it exists. I support dropping it
  as a stamped rule and keeping the "Order" bullet in Deployment as wording.
- **Trivy**: keep the rule as conditional ("binds if CI ever builds an image").
  It costs nothing today and it binds automatically if Chromium option (c) is
  ever chosen.
- **CQ-10** (two `noqa: BLE001` comments without a reason, in the publish hook
  and the lint hook): fix them in this intent. Both hooks are security gates,
  and a broad `except` there must document why failing that way is safe.
- **No additional SAST engine is needed.** CodeQL is free for a public
  repository and could be a non-required extra, but bandit plus ruff's `B` and
  `S`-adjacent rules match the code base's size. I do not ask for it.
- **DAST**: the planned Playwright post-deploy check, which confirms an
  unauthenticated or non-allowlisted visitor is refused, is the only dynamic
  test. That is proportionate. It must assert the refusal on every deploy, not
  only that the app answers.

## Positions

- AGREE: Align `team.md` Deployment with `project.md` (public apps, `st.login`, verified email, email allowlist); `project.md` is the later, deliberate decision.
- OBJECT: The Deployment "Who can reach it" bullet as drafted is not testable; add the gate properties from section 2 (fail closed before any render, `email_verified` required, normalised exact-match allowlist, per-environment cookie and signing secrets).
- AGREE: Walking Skeleton [CHANGE] to "verified email not on the allowlist"; it states the security property the skeleton must prove.
- AGREE: Candidate M1 (burned literal and its `TEMPORARY_EXCLUSIONS` entry leave in one commit); the code fails on a partial removal, and the gitleaks allowlist stays.
- OBJECT: The "outside local development" carve-out in the signing-secret rule; once the literal is gone no committed default may exist, so every entry point should fail closed and local development should use an ignored `.env.local`. The interview should decide this.
- AGREE: Tests get a throwaway secret generated per run and placed in `os.environ` early in `conftest.py`, with the condition that the value is generated, never a committed constant.
- AGREE: Candidate F2 (never commit `.streamlit/secrets.toml` or `.env.local`), widened to `.env` and `.env.*`, with explicit `.gitignore` lines outside the AI-DLC block.
- AGREE: Candidate F1 (the post-deploy check never signs in as an allowlisted user; CI holds no identity-provider credentials).
- AGREE: Candidate M2 (renaming a required job and changing the ruleset happen in the same piece of work).
- AGREE: Drop M3 as a stamped rule; R-SEC-1 and R-SEC-3 already forbid a hosted app before the gate and the secret handling merge.
- AGREE: Code Style [NEW] on dependencies (Authlib in the runtime lock, playwright in the dev lock, both under pip-audit, both locks committed together).
- AGREE: Chromium option (a), with the rule recording that it is installed only in jobs that hold no secrets and `contents: read`.
- OBJECT: The `browser-tests` watch list as carried forward; add `requirements-dev.txt` and `.github/workflows/ci.yml`, or a Playwright bump passes the required check untested.
- AGREE: Dependabot ignores semver-major for `mcp` only; `streamlit` majors stay open because Streamlit is the internet-facing runtime and the `st.login` boundary.
- AGREE: Keep Trivy as a rule that binds only when CI builds an image.
- AGREE: Fix CQ-10 in this intent; both hooks are security gates.
- AGREE: Code Style [NEW] on `security-exceptions.toml` as the only waiver, with inline `# nosec` having no effect.
