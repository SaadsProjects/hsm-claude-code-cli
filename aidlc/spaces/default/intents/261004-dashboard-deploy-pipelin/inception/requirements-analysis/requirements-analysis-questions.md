# Requirements Analysis — Questions

Initial request: "set up a deployment pipeline for the dashboard". The practices you approved already settle the following, so they aren't asked again:
- the host (Streamlit Community Cloud)
- staging plus a manually approved production
- PR-gated `main`
- the CI checks
- moving the secret to the environment
- persisting data and the audit log

These questions cover what's still needed to write testable requirements.

Facts checked while preparing them:
- Streamlit 1.64.0 is installed and has built-in sign-in (`st.login`, OpenID Connect).
- The backend's bind address is hard-coded in `mock_hsm/server.py:720`.
- All backend data lives in Python dicts and lists in `mock_hsm/db.py`, with writes in `mock_hsm/writes.py`.
- Streamlit Community Cloud's free tier allows only a limited number of private (viewer-allowlisted) apps. Two private apps may not be available.

---

### Question 1
Keeping data and the audit log across redeploys means replacing the in-memory store with a real database, which touches every write route. How should this be scoped?

A. Split it into its own follow-up piece of work. This pipeline ships with data resetting on each deploy, and the persistence requirement is recorded as deferred
B. Persist only the audit log in this piece of work (an external store), and split the data persistence out
C. Do both in this piece of work (a hosted database such as a free-tier Postgres)
X. Other (please specify)

[Answer]: A

### Question 2
How should strangers be kept out, given the limits on private Streamlit Cloud apps?

A. Built-in Streamlit sign-in (`st.login` with Google or another OpenID provider) plus an email allowlist checked in the app, so it works even if the apps are technically public
B. Streamlit Cloud's viewer allowlist (private apps), accepting that the free tier may not allow two
C. Both: private apps where possible, with the in-app sign-in as well
X. Other (please specify)

[Answer]: A

### Question 3
Who should be on the sign-in allowlist?

A. Only me
B. Me plus a short list of named reviewers, kept in Streamlit secrets
X. Other (please specify)

[Answer]: A

### Question 4
After someone signs in, how should the in-app persona picker behave?

A. Keep it as is, so any signed-in person can act as any persona (it's a demo)
B. Keep it, but hide the developer/test persona (`user_dev_tester`) on hosted apps
C. Tie each signed-in email to one fixed persona
X. Other (please specify)

[Answer]: A

### Question 5
How should production be promoted?

A. A manual GitHub Actions run with a required approval (a protected GitHub Environment) that fast-forwards the production branch to a commit that already passed CI and the staging check
B. A pull request from `main` into the production branch that I merge by hand
X. Other (please specify)

[Answer]: A

### Question 6
How should local development get the signing secret once it leaves the source code?

A. Always require it, locally too, from a gitignored `.streamlit/secrets.toml` or an env var. Tests generate their own
B. An explicit local-dev switch (for example `HSM_ENV=local`) allows a dev-only fallback. Anything without that switch fails closed
X. Other (please specify)

[Answer]: A

### Question 7
What should the post-deploy check prove? (It must stay read-only.)

A. The app answers its health endpoint and serves the sign-in page to an anonymous visitor (no dashboard data visible)
B. As A, plus a signed-in, read-only data check using a dedicated test account
X. Other (please specify)

[Answer]: A

### Question 8
Streamlit Community Cloud apps go to sleep when idle, and redeploys take a few minutes. What reliability do you expect?

A. Best effort for a demo: no uptime target, and the post-deploy check waits up to about 10 minutes for the app to wake and redeploy
B. A stated availability target that we monitor
X. Other (please specify)

[Answer]: A

### Question 9
The repo also contains the Claude Code side: the MCP server, subagents and slash commands. What is deployed?

A. Only the dashboard with its in-process mock backend. The MCP server and agent workflows stay local-only, with CI tests only
B. The dashboard and also a hosted mock backend that the local MCP server can reach
X. Other (please specify)

[Answer]: B

### Question 10
The signing secret already in the public repo history can't be un-published. What should happen to it?

A. Treat it as burned: remove it from the code, never use it anywhere again (hosted apps get a brand-new secret, and local dev and tests supply their own, per Question 6), and add a documented allowlist entry so secret scanning doesn't flag the old history on every run
B. Also rewrite git history to remove it
X. Other (please specify)

[Answer]: A

---

## Follow-up Questions

### Question 11
Your Q9 answer (a hosted backend the local MCP server can reach) conflicts with the hard rule approved in the last stage: "NEVER make the mock backend reachable from outside the dashboard's own host, container or process". Streamlit Cloud also can't expose a second server, so a reachable backend needs another host. How should this be resolved?

A. Deploy only the dashboard with its in-process backend after all, and keep the rule
B. Defer the hosted backend to its own follow-up piece of work (which would also have to revisit that rule). This pipeline deploys only the dashboard
C. Include a separately hosted, authenticated backend now (needs a second host, such as a small container service, and a change to the approved rule)
X. Other (please specify)

[Answer]: A

### Question 12
Your Q1 answer (split persistence out) conflicts with the approved team practice "data and audit log both survive a redeploy". How should this be recorded?

A. Keep the team practice as the goal. This piece of work records persistence as a known, deferred gap: staging and production reset on each deploy until the follow-up lands
B. Change the team practice itself to "reset on deploy is acceptable for now" (this means revisiting the approved practices)
X. Other (please specify)

[Answer]: A

---

## Consolidated Summary Confirmation

**Mode:** guided

- **Persistence:** split out into its own follow-up. Staging and production reset on each deploy. This is recorded as a known deferred gap, and the team practice stays the goal (Q1: A, Q12: A).
- **Keeping strangers out:** Streamlit's built-in sign-in (`st.login`, OpenID Connect) plus an email allowlist checked in the app. This works even though the Cloud apps are public (Q2: A).
- **Allowlist:** only you (Q3: A).
- **Persona picker:** unchanged. Any signed-in person can act as any persona (Q4: A).
- **Production promotion:** a manual GitHub Actions run with a required approval (protected Environment). It fast-forwards the production branch to a commit that already passed CI and the staging check (Q5: A).
- **Signing secret, locally:** always required, from a gitignored `.streamlit/secrets.toml` or an env var. Tests generate their own (Q6: A).
- **Post-deploy check:** the health endpoint answers, and an anonymous visitor sees only the sign-in page with no data. It is read-only (Q7: A).
- **Reliability:** best effort for a demo, with no uptime target. The post-deploy check waits up to about 10 minutes for wake or redeploy (Q8: A).
- **What gets deployed:** only the dashboard with its in-process backend. The MCP server and agent workflows stay local and CI-tested. The backend-isolation rule holds (Q9: B, superseded by Q11: A).
- **Old secret:** treated as burned. It is removed from the code and never used again. Hosted apps get a new secret, and the old history gets a documented secret-scan allowlist entry (Q10: A).

Does this all look correct before I generate the requirements artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
