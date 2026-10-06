# NFR Requirements — Questions

These questions turn the approved requirements into measurable targets. Most of them close the gaps the product lead flagged in `requirements.md`, which you approved with those findings still open (R-01 to R-11).

---

### Question 1
Should local runs (`streamlit run dashboard/app.py` on your machine) also require sign-in? (R-03)

A. Yes. Local runs need the same OIDC settings in a gitignored `.streamlit/secrets.toml`. The dashboard tests use a test-only hook that supplies a signed-in user, and that hook can't be switched on from configuration
B. No. Sign-in is skipped only when an explicit local-only switch is set and the app is bound to `127.0.0.1`. A hosted app refuses to start if that switch is set
X. Other (please specify)

[Answer]: A

### Question 2
How should the post-deploy check know the redeploy has finished, so it doesn't credit the old build to the new commit? (R-02)

A. The app shows its build's commit SHA on the sign-in page (read from git at startup). The check waits until that SHA equals the commit under test before checking anything else
B. Don't verify it. Mark the staging evidence as best effort
X. Other (please specify)

[Answer]: A

### Question 3
How should the check prove that an anonymous visitor sees only the sign-in prompt? Streamlit draws its content over a websocket, so a plain web request can't see it. (R-01)

A. A headless browser in CI (Playwright) loads the app anonymously. It asserts the sign-in button and the build SHA are visible, and that none of a fixed list of data markers (site names, persona names, tab titles) appear
B. HTTP only: the health endpoint returns OK and the page shell loads. The "no data before sign-in" rule is proven by unit tests instead
X. Other (please specify)

[Answer]: A

### Question 4
On a personal GitHub account, branch rules can't name a specific workflow as the only allowed writer. How should the `production` branch be protected? (R-04)

A. A ruleset blocks all pushes, force-pushes and deletion on `production`. The only bypass is a deploy key whose private half lives in the protected `production` Environment's secrets, so the promotion workflow can use it only after you approve. Rollback is a forced update made through that same key
B. A ruleset blocks force-pushes and deletion only. The promotion workflow pushes with its built-in token, and you as admin can also push. Rollback is a revert commit, not a forced move
X. Other (please specify)

[Answer]: A

### Question 5
When should the security scanners fail the build? (R-07)

A. bandit fails on medium-or-higher severity with medium-or-higher confidence. pip-audit fails on any known vulnerability. A vulnerability that can't be fixed goes into a checked-in ignore list with a reason and an expiry date at most 90 days out; an expired entry fails the build
B. bandit fails on high severity only, and pip-audit on high or critical only, with the same ignore-list rules
X. Other (please specify)

[Answer]: B

### Question 6
When does the 80% coverage gate switch on, and what if the first measurement is below 80%? (R-06)

A. The first pipeline PR measures the baseline. If it is 80% or more, the gate switches on in that same PR. If it is lower, a "coverage must not drop" gate applies at once, and tests are added until 80% is reached, before production is ever promoted
B. The gate switches on at 80% in the first PR no matter what, so that PR can't merge until coverage reaches 80%
X. Other (please specify)

[Answer]: A

### Question 7
Which Python versions do the lockfiles and the hosted apps use? (R-08)

A. One universal lockfile (`uv pip compile --universal`) that resolves for every version from 3.10 to 3.14. The hosted apps run the newest Python that Streamlit Cloud offers, and CI adds that version to its matrix if it isn't 3.10 or 3.14
B. A separate lockfile per Python version, with the hosted apps pinned to 3.14
X. Other (please specify)

[Answer]: A

### Question 8
Should hosted users be told that data resets? (R-11)

A. Yes. A visible banner reads "Demo data — resets on every redeploy or restart", and it stays until persistence lands
B. No notice
X. Other (please specify)

[Answer]: A

### Question 9
What page-speed target should a signed-in user get on an app that is already awake?

A. The first dashboard view renders within 5 seconds at p95, excluding Streamlit Cloud cold start, which is covered by the 10-minute wake allowance
B. No page-speed target (it's a demo)
X. Other (please specify)

[Answer]: A

### Question 10
How long should a sign-in last?

A. Accept Streamlit's built-in sign-in cookie lifetime. The allowlist is re-checked on every page interaction, so removing an email takes effect on that user's next interaction
B. Force a fresh sign-in after 24 hours, in addition to the per-interaction allowlist check
X. Other (please specify)

[Answer]: A

### Question 11
Beyond the post-deploy check, how should you find out if production breaks?

A. GitHub's own failure emails, plus a scheduled read-only check of production every 6 hours that fails visibly (and emails you) when it breaks
B. Only the checks that run with each deploy or promotion, with no scheduled check
X. Other (please specify)

[Answer]: A

### Question 12
How should the data in the hosted apps be classified?

A. Everything is synthetic, seeded demo data: no real staff, wages or vendors. The only personal data is your sign-in email (held in secrets) and the signed-in email shown in the app. Classification: internal
B. Some of the data is real or derived from real data (please describe)
X. Other (please specify)

[Answer]: A

---

## Follow-up Questions

### Question 13
Your Q11 answer (a scheduled check of production every 6 hours that emails you on failure) conflicts with the approved requirements, which list "uptime monitoring, alerting, or an availability target" as out of scope. How should this be resolved?

A. Keep the scheduled check. Record it as a deliberate, small addition to the approved scope: a read-only check that runs every 6 hours, alerts through GitHub's failure email, and sets no availability target
B. Drop it and keep the approved scope. Production is checked only when it is promoted
X. Other (please specify)

[Answer]: A

---

## Consolidated Summary Confirmation

**Mode:** guided

- **Local sign-in:** always required, using the same OIDC settings in a gitignored `.streamlit/secrets.toml`. Dashboard tests use a test-only hook that supplies a signed-in user and cannot be enabled through configuration (Q1: A).
- **Build identity:** the app shows its commit SHA on the sign-in page. Every post-deploy check first waits until that SHA equals the commit under test (Q2: A).
- **Anonymous check:** Playwright in CI loads the app with no session. It asserts the sign-in button and the build SHA are visible, and that none of a fixed list of data markers appear (Q3: A).
- **Production branch:** a ruleset blocks all pushes, force-pushes and deletion. The only bypass is a deploy key held in the approval-gated `production` Environment. Rollback is a forced update made through that key (Q4: A).
- **Scanners:** bandit fails on high severity. pip-audit fails on high or critical vulnerabilities. A vulnerability that can't be fixed goes in a checked-in ignore list with a reason and an expiry date at most 90 days out, and an expired entry fails the build (Q5: B).
- **Coverage:** the first PR measures the baseline. At 80% or more, the gate switches on at once. Below 80%, a "must not drop" gate applies, and coverage must reach 80% before any production promotion (Q6: A).
- **Python:** one universal lockfile (`uv pip compile --universal`) for 3.10 to 3.14. The hosted apps run the newest Python that Streamlit Cloud offers, and that version is added to the CI matrix if it isn't already there (Q7: A).
- **Reset notice:** a banner reads "Demo data — resets on every redeploy or restart" until persistence lands (Q8: A).
- **Page speed:** the first dashboard view renders within 5 s at p95 on an awake app. Cold start is excluded (Q9: A).
- **Sign-in lifetime:** Streamlit's default cookie lifetime. The allowlist is re-checked on every interaction (Q10: A).
- **Monitoring:** a read-only check of production runs every 6 hours, with failure alerts by GitHub email and no availability target. This is recorded as a deliberate, small addition to the approved scope (Q11: A, Q13: A).
- **Data classification:** all data is synthetic, seeded demo data, classified internal. The only personal data is the owner's sign-in email (Q12: A).

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
