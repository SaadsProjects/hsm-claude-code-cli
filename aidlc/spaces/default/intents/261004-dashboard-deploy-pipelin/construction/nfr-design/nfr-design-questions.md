# NFR Design — Questions

The approved NFR requirements fix almost every target, so these questions cover only the design choices that are still open. Choices with a single sensible answer are decided in the design documents and listed there as decisions:
- where the sign-in gate sits;
- how the backend thread is started once;
- the fingerprint file globs and the digest-based source check (reviewer item R-10);
- cancelling superseded CI runs.

---

### Question 1
How should the promotion workflow know a commit passed the staging check?

A. The staging check posts a GitHub commit status named `staging-check` on the commit it verified. Promotion requires that status, plus every required CI check, to be `success` on the chosen commit
B. Promotion searches the Actions run history for a successful `staging-check.yml` run on that commit
X. Other (please specify)

[Answer]: A

### Question 2
Which commit does a promotion pick by default?

A. The newest commit on `main` that has passed CI and the staging check. An optional input lets you name a specific commit, which must pass the same checks
B. Always the newest commit on `main`, with no input
X. Other (please specify)

[Answer]: A

### Question 3
How should promotions be recorded, and what is a valid rollback target?

A. Each successful promotion creates an annotated tag `prod-<UTC timestamp>` on the promoted commit. Rollback accepts only a commit that carries one of those tags, so you can only roll back to something that was in production before
B. Don't create tags; rely on GitHub's Environment deployment history. Rollback accepts any commit that passed CI and the staging check
X. Other (please specify)

[Answer]: A

### Question 4
How should dependency and Action pins be kept current?

A. Dependabot opens weekly update PRs for the pip lockfile inputs and for the GitHub Actions SHA pins. Each PR goes through the full CI
B. No automation; update pins by hand when needed
X. Other (please specify)

[Answer]: A

### Question 5
How should a developer get the local signing secret?

A. A script, `scripts/dev-secret.sh`, generates a secret once into a gitignored `.env.local` and prints the `export` line. The runbook and `CLAUDE.md` tell you to source it before starting the mock server and `claude`
B. Only document a one-line command (`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`). You keep the value yourself
X. Other (please specify)

[Answer]: A

### Question 6
When the scheduled production check fails, what should happen besides the failure email?

A. Nothing automatic. You decide whether to roll back, using the promotion workflow
B. Automatically open a GitHub issue labelled `prod-check-failure` (and comment on it again if it is still open on later failures)
X. Other (please specify)

[Answer]: B

---

## Consolidated Summary Confirmation

**Mode:** guided

- **Staging evidence:** the staging check posts a `staging-check` commit status. Promotion requires it, plus every required CI check, to be `success` (Q1: A).
- **Promotion target:** by default, the newest commit on `main` that has passed CI and the staging check. An optional input can name a specific commit, which must pass the same checks (Q2: A).
- **Promotion record and rollback:** each promotion creates an annotated tag `prod-<UTC timestamp>`. Rollback accepts only a commit that carries such a tag (Q3: A).
- **Pin updates:** Dependabot opens weekly PRs for the pip lockfile inputs and the Action SHA pins, and each PR goes through full CI (Q4: A).
- **Local secret:** `scripts/dev-secret.sh` generates a secret once into a gitignored `.env.local` and prints the export line. The runbook and `CLAUDE.md` tell you to source it (Q5: A).
- **Failed production check:** besides GitHub's failure email, the workflow opens a GitHub issue labelled `prod-check-failure`, or comments on it if one is already open. It needs `issues: write` for that job only (Q6: B).

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
