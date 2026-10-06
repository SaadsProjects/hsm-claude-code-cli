# Practices Discovery — Questions

These questions cover only what the repository could not answer. Each one has an evidence note. Full detail is in `evidence.md` and `contributions/`.

Fact found while preparing these: `SaadsProjects/hsm-claude-code-cli` is **public** (`gh repo view`). The backend's token-signing secret is a literal in `mock_hsm/auth.py:23`, and the dashboard holds it in-process (`dashboard/session.py`). So anyone can already mint an admin token for any copy that is reachable.

---

## Who uses it and where it runs

### Question 1
Who should be able to reach the deployed dashboard? (Today it has no password. Anyone who opens it can pick any persona and write data.)

A. Only me, on my own machine (localhost)
B. A private network only (home LAN, VPN or tailnet)
C. The internet, but only behind a login layer in front of it (for example a proxy with sign-in)
D. The open internet as it is today, with no login
X. Other (please specify)

[Answer]: C

### Question 2
Where should the dashboard (and its mock backend) run?

A. A Docker container on my own machine, started by the pipeline or by one command
B. A single cloud VM (for example AWS EC2 or Lightsail)
C. A managed AWS container service (App Runner or ECS Fargate)
D. Streamlit Community Cloud
E. Nowhere yet: build and test in CI and produce a ready-to-run image, and pick a host later
X. Other (please specify)

[Answer]: D

### Question 3
How many environments do you want?

A. One environment
B. Two: staging deploys automatically on merge, and production needs my manual approval
C. Only a throwaway preview per change
X. Other (please specify)

[Answer]: B

### Question 4
The backend's signing secret is in public source. What should the deploy do about it? (Moving it needs a small code change in `mock_hsm/auth.py`.)

A. Move the secret into an environment variable (from a secrets store when hosted) and refuse to start without it outside local dev
B. Keep the demo secret, but only ever run on localhost or a private network
C. Decide later; this pipeline doesn't touch it
X. Other (please specify)

[Answer]: A

### Question 5
The backend keeps its data in memory and writes an audit log. What should happen to them on each redeploy?

A. A reset is fine for both (it's a demo)
B. Data resets, but the audit log persists on a volume
C. Both should persist (this needs more than a volume, because data is in memory today)
X. Other (please specify)

[Answer]: C

## How changes reach `main`

### Question 6
How should changes reach `main` once CI exists? (Your team defaults require CI to pass before merging. Lately you have pushed straight to `main`.)

A. Pull request with required CI checks and a protected `main`, squash-merged
B. Pull request with required CI checks and a protected `main`, keeping merge commits
C. Keep pushing straight to `main` and let CI run after the push (recorded as a deliberate exception to "CI before merge")
X. Other (please specify)

[Answer]: A

### Question 7
Build a thin end-to-end slice first? A walking skeleton is a minimal version that runs the whole way through, built first to prove the pieces connect before the real features go in.

A. Yes. The slice is: commit, then lint and tests, then build, then deploy to one environment, then a read-only health check
B. Yes, and the slice must also prove the security checks run and that the backend port is not reachable from outside
C. No, build the pipeline piece by piece
X. Other (please specify)

[Answer]: B

## Testing

### Question 8
How do you write tests? (History shows tests land in the same commit as the code, which doesn't show which came first.)

A. Code first, then tests for it before committing (test-after)
B. Test first (TDD)
C. A mix (please describe)
X. Other (please specify)

[Answer]: B

### Question 9
The 80% line-coverage floor is a fixed requirement for this kind of work. There is no coverage tool yet. What should count toward it?

A. All app code (`agents/`, `dashboard/`, `mock_hsm/`, `mcp_server/` and `.claude/hooks/`), with subprocess-run code measured properly
B. Only `agents/` and `dashboard/`
C. Measure a baseline first with no gate, then decide which packages count before the gate is switched on
X. Other (please specify)

[Answer]: A

### Question 10
Which Python version(s) should CI and the deploy image use? (The suite has only been run on 3.14. The code claims 3.10+.)

A. 3.14 only (what's actually tested)
B. A matrix of 3.10 and 3.14, so the 3.10+ claim is checked; the image uses 3.14
C. A single middle version (for example 3.12)
X. Other (please specify)

[Answer]: B

### Question 11
How should timing (perf) tests and flaky tests be handled in CI?

A. Perf tests run manually or nightly as advisory only and never block. A failing test is never auto-retried: fix it or quarantine it
B. Perf tests never run in CI. Flaky tests may be retried once
C. Perf tests block like everything else
X. Other (please specify)

[Answer]: B

## Code style and supply chain

### Question 12
How should dependency versions be handled? (Today ruff, pytest and streamlit only have lower bounds, so CI can break with no code change.)

A. A hash-pinned lockfile (for example pip-tools), with runtime and dev requirements split
B. Pin exact versions in `requirements.txt`, with no lockfile
C. Keep floating versions
X. Other (please specify)

[Answer]: A

### Question 13
Which security checks should CI run before any deploy? (select all that apply)

A. Secret scanning (gitleaks, plus GitHub push protection)
B. Dependency vulnerability audit (pip-audit)
C. Static security analysis (bandit as a separate CI job; adding ruff `S` rules would change every commit's lint output)
D. GitHub Actions pinned by commit SHA, least-privilege permissions, and short-lived OIDC deploy credentials
E. Container image scan (Trivy) if an image is built
X. Other (please specify)

[Answer]: A, B, C, D, E

### Question 14
Should a code formatter be added?

A. No: lint only, as today
B. Yes: adopt `ruff format` and check it in CI
X. Other (please specify)

[Answer]: B

## Hard rules

### Question 15
Which candidate hard rules should become permanent "always / never" rules? (select all that apply; full text in `discovered-rules.md` and `contributions/`)

A. The existing repo rules: commit via `/commit`, never bypass the lint gate, keep the publish/submit `ask` rules, never call publish/submit from a pipeline or smoke check, point test audit trails at temp files in CI, and give the dashboard no publish/PO path
B. Testing rules: perf tests never block, never weaken the coverage floor or its package set to pass a run, and run CI pytest with no unrelated `-m` filter
C. Security rules: no network exposure without a login layer, backend never reachable from outside, no hosted deploy with the hard-coded secret, SHA-pinned Actions, OIDC-only deploy credentials, and CI as the authoritative gate
D. None: keep everything as practices, not hard rules
X. Other (please specify)

[Answer]: A, B, C

---

## Consolidated Summary Confirmation

**Mode:** guided

- **Reach:** the internet, but only behind a sign-in layer (Q1: C).
- **Host:** Streamlit Community Cloud (Q2: D). The mock backend runs in-process, and the viewer allowlist provides the sign-in layer.
- **Environments:** staging deploys automatically on merge, and production needs a manual approval (Q3: B). Staging and production are two Cloud apps on two branches.
- **Signing secret:** moved out of source into an env var or Streamlit secrets. Startup fails closed outside local dev (Q4: A). This needs a code change in `mock_hsm/auth.py`.
- **Persistence:** data and the audit log both survive redeploys (Q5: C). This needs a real datastore; Requirements Analysis will size it.
- **Path to main:** a pull request with required CI checks and a protected `main`, squash-merged (Q6: A).
- **Thin slice first:** yes. Commit → lint and tests → deploy to staging → read-only health check, also proving the security checks run and the sign-in layer blocks strangers (Q7: B).
- **Testing:** test first, TDD (Q8: B).
- **Coverage:** an 80% line floor over all app code, `agents/`, `dashboard/`, `mock_hsm/`, `mcp_server/` and `.claude/hooks/`, with subprocess-run code measured (Q9: A).
- **Python:** a CI matrix of 3.10 and 3.14 (Q10: B).
- **Perf and flaky tests:** perf tests never run in CI, and a flaky test may retry once (Q11: B).
- **Dependencies:** a hash-pinned lockfile, with runtime and dev requirements split (Q12: A).
- **Security checks before deploy:** secret scanning, dependency audit, bandit, hardened Actions (SHA pins, least privilege, OIDC), and a Trivy scan of any built image (Q13: A, B, C, D, E).
- **Formatter:** adopt `ruff format` and check it in CI (Q14: B).
- **Hard rules promoted:** the existing repo rules, the testing rules and the security rules (Q15: A, B, C).

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
