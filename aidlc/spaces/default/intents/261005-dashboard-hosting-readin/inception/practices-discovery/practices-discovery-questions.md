# Practices Discovery Questions — Dashboard Hosting Readiness (re-run)

## Sources

- Baseline: `aidlc/spaces/default/memory/team.md` (affirmed 2026-10-04) and `project.md`
- Lead draft: `team-practices.md`, `discovered-rules.md`, `evidence.md` in this folder
- Independent reviews: `contributions/aidlc-quality-agent.md`, `contributions/aidlc-developer-agent.md`, `contributions/aidlc-devsecops-agent.md`
- Code knowledge base: `aidlc/spaces/default/codekb/hsm-claude-code-cli/`

Only the points the draft and the three reviews couldn't settle are asked here. Everything else in the draft is carried forward. Where all three reviewers agreed (for example: keep the container-scan rule only for if an image is ever built; fix the two `noqa` comments that lack a reason in this work), the draft is updated without asking.

## Q1. How should finished pieces of work reach `main`?

The workflow normally merges each finished piece of work into `main` locally, but `main` refuses direct pushes, so every change has to arrive by pull request. The quality and security reviewers both favour C.

A. One working branch for the whole intent, shipped as one pull request at the end
B. Every piece of work as its own branch and pull request
C. A few grouped pull requests: the burned-secret removal first, on its own, then the rest in natural groups
X. Other (please specify)

[Answer]: A

## Q2. Build a thin end-to-end slice first for this work? A walking skeleton is a minimal version that runs the whole way through, built first to prove the pieces connect before the real features go in.

The team's usual slice ends at a staging app, but this work only creates the hosted apps at the very end.

A. Yes, a local slice: the first pull request (the secret removal) merges with all 10 required checks green, and the dashboard starts locally behind the sign-in screen
B. Yes, the usual staging slice, accepting that it can only be proven at the end of this work
C. No slice for this work; build the pieces in order
X. Other (please specify)

[Answer]: A

## Q3. Which check proves a finished piece of work end to end?

A local test run doesn't exercise the secret scan, the dependency audit or the lockfile check; the CI run on the pull request does. The quality reviewer recommends A.

A. The CI run on the pull request, with all 10 required checks green
B. The local test suite (`python -m pytest tests/ -q`)
C. The post-deploy check against staging, once it exists
X. Other (please specify)

[Answer]: A

## Q4. Should demo data and the audit trail survive a redeploy?

The team rule says both survive a redeploy, but the backend keeps them in memory, and this work adds a "demo data resets" banner.

A. No: accept that both reset on redeploy, keep the banner (tested), and change the rule to match
B. Yes: keep the rule, and add a persistent store for data and the audit trail in this work (new scope)
C. Only the audit trail survives; demo data resets (smaller new scope)
X. Other (please specify)

[Answer]: A

## Q5. How are the hosted apps protected?

The team file says private apps with a viewer allowlist; the project file (decided later) says public apps with Streamlit's own sign-in, a verified email, and an email allowlist.

A. Public apps with Streamlit's sign-in, verified email and an email allowlist; the allowlist lives in each app's Streamlit secrets and you maintain it
B. Private apps with Streamlit Cloud's viewer allowlist
X. Other (please specify)

[Answer]: A

## Q6. Who approves a production release?

The organisation default is two people (a tech lead and a product owner), but you are the only stakeholder.

A. You alone
B. Two people (name the second under Other)
X. Other (please specify)

[Answer]: A

## Q7. Is there any built-in fallback signing secret for local development?

The security reviewer objects to the current wording ("outside local development the app refuses to start"): once the burned value is gone, no default should exist anywhere.

A. No fallback anywhere: every entry point refuses to run without a secret; local development uses a git-ignored `.env.local` made by the dev-secret script, and tests generate a throwaway secret per run
B. Keep a fallback for local development only
X. Other (please specify)

[Answer]: B

## Q8. Should the team file state the current floor numbers?

The quality reviewer points out that numbers written into the team file go stale (the old "757 tests" did).

A. No: point to `.test-floor` and `.coverage-floor`; keep measured figures in the evidence file
B. Yes: write the current numbers into the team file
X. Other (please specify)

[Answer]: A

## Q9. How should CI get the browser for browser tests?

The browser download sits outside the hash-pinned lockfile and the dependency audit.

A. Install it with Playwright, cached by Playwright version, only in jobs that hold no secrets
B. Run browser tests in Playwright's container image pinned by digest (brings the container-scan rule into play)
X. Other (please specify)

[Answer]: A

## Q10. Should the automated dependency updates skip major-version bumps?

An `mcp` 2.x update is open now, and 2.x would break the tool server. The reviewers disagree about Streamlit: the quality reviewer would skip its majors too; the security reviewer wants them kept visible because Streamlit is the internet-facing part.

A. Skip majors for `mcp` only
B. Skip majors for both `mcp` and `streamlit`
C. Skip no majors
X. Other (please specify)

[Answer]: C

## Q11. Which of these become hard project rules? (select all that apply)

- M1: always remove the burned secret and its scan exclusion in the same commit
- M2: always change a required CI job's name and the branch-protection check list together
- F1: never let the post-deploy check sign in as an allowlisted user, or store sign-in credentials in CI
- F2: never commit `.streamlit/secrets.toml`, `.env.local`, `.env` or `.env.*`; ignore them with explicit `.gitignore` lines

(A third mandate, "create the hosted apps only after the sign-in gate and secret handling merge", is dropped as a rule because existing project rules already forbid hosting before that.)

A. M1
B. M2
C. F1
D. F2
E. None of them
X. Other (please specify)

[Answer]: A, B, C, D

## Q12. Should the post-deploy check script count toward the coverage measurement?

`scripts/` isn't in the coverage measurement today, so the script would be held only to its own tests (the happy path plus two error cases). Adding `scripts/` changes the coverage percentage.

A. No: leave `scripts/` out of coverage; the script has its own tests
B. Yes: add `scripts/` to the coverage measurement
X. Other (please specify)

[Answer]: A

## Q13. What happens to branches after they merge?

`ci-pipeline` is merged but still on GitHub, and `backup/pre-rollback-2026-10-03` is still local.

A. Delete branches automatically after merge on GitHub; delete `ci-pipeline`; keep the backup branch
B. Same, and delete the backup branch too
C. Leave branches as they are
X. Other (please specify)

[Answer]: A

## Q14. Follow-up to Q1, Q2 and Q3: one pull request at the end, or the secret removal first?

Q1 chose one pull request for the whole intent at the end. But the scope decision (D9) says the burned-secret removal lands first and sooner than the rest, Q2's local slice needs that first pull request merged with all 10 checks green, and Q3 proves each piece with the pull-request CI run. One pull request at the end can't do those.

A. The secret removal ships first as its own pull request; everything else ships as one pull request at the end
B. One pull request at the end for everything; the secret removal lands with the rest, and the slice and the per-piece proof use CI runs on that open pull request instead
C. Switch to grouped pull requests (Q1 option C)
X. Other (please specify)

[Answer]: A

## Q15. Follow-up to Q7: what exactly is the local fallback?

Q7 keeps a fallback secret for local development. The earlier deploy design (intent 261004, requirements Q6) decided there would be no built-in fallback, even locally, and the burned value must not be the fallback (project rule correction about Q10/Q6).

A. No committed fallback after all: local development uses the ignored `.env.local` from the dev-secret script (same as Q7 option A)
B. A fallback that is generated at random when the app starts locally (never committed). This only works if every local process (dashboard, backend, hooks, tool server) shares it.
C. A fixed, clearly-marked development value committed in the code, used only when not hosted (not the burned value)
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Reaching `main` (Q1, refined by Q14): the burned-secret removal ships first as its own pull request; everything else ships as one pull request at the end. Q14 supersedes the "one pull request for everything" reading of Q1; both answers stay visible above.
- Thin slice first (Q2): yes, a local slice. The secret-removal pull request merges with all 10 required checks green, and the dashboard starts locally behind the sign-in screen.
- Proof of a finished piece (Q3): the CI run on the pull request, with all 10 required checks green.
- Data and audit trail (Q4): both reset on redeploy. The reset banner stays and is tested, and the team rule changes to match.
- Hosted app protection (Q5): public apps with Streamlit's sign-in, a verified email and an email allowlist. The allowlist lives in each app's Streamlit secrets, and you maintain it.
- Production approver (Q6): you alone.
- Local signing secret (Q7, superseded by Q15): no committed fallback anywhere. Every entry point refuses to run without a secret. Local development uses the ignored `.env.local` from the dev-secret script, and tests generate a throwaway secret per run.
- Floor numbers (Q8): the team file points to `.test-floor` and `.coverage-floor`; measured figures stay in the evidence file.
- Browser in CI (Q9): install it with Playwright, cached by Playwright version, only in jobs that hold no secrets.
- Major-version bumps (Q10): skip none; every major update still arrives as a pull request.
- Hard rules (Q11): M1, M2, F1 and F2 all become project rules.
- Coverage of `scripts/` (Q12): left out; the post-deploy check script is held to its own tests.
- Branches (Q13): GitHub auto-deletes merged branches, `ci-pipeline` is deleted, and the backup branch is kept.
- Carried forward without asking, because all three reviewers agreed: the container-scan rule applies only if an image is ever built; the two `noqa` comments that lack a reason get fixed in this work.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
