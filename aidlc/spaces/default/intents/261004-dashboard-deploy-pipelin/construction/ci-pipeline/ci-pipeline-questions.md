# CI Pipeline — Questions

**Already answered.** The standard questions for this stage (CI tool, branch strategy, merge gates, artifact store) were settled earlier:
- CI tool: GitHub Actions.
- Branch strategy: trunk on a protected `main`, squash-merged.
- Merge gates: everything in `cicd-pipeline.md`.
- Artifact store: none, because Streamlit Cloud builds from the branch.

**Scope decision for this stage.** The application code changes are split into a separate follow-up piece of work. This stage writes only the CI workflow, its gate scripts and their tests, the lockfiles, and the CI config files.

**Facts checked while preparing these questions:**
- `uv` is installed locally. `actionlint` and `gitleaks` are not; CI installs pinned releases of both.
- The repository already has an **active ruleset** named `main_branch_protection`. It blocks deletion and force-push, but its target list is **empty**, so it currently protects nothing.
- `mock_hsm/auth.py:23` still holds the burned secret. It stays there until the follow-up lands.

---

### Question 1
The burned-secret source check would fail on `mock_hsm/auth.py` until the follow-up removes the literal. How should CI handle that meanwhile?

A. Add the check now, with one temporary, documented exclusion for `mock_hsm/auth.py`. The follow-up removes the exclusion in the same change that removes the literal, and a CI test fails if the exclusion outlives the literal
B. Leave the burned-secret check out until the follow-up adds it. gitleaks, with its value allowlist, still runs now
X. Other (please specify)

[Answer]: A

### Question 2
How should the new CI land and become enforced?

A. Open it as a pull request from a `ci-pipeline` branch. Merge it once CI is green on the PR itself. Then change the existing `main_branch_protection` ruleset to target `main` and require the new checks with squash-only merging. I'd give you the exact settings checklist for that change, but you would apply it yourself, since it changes repository settings
B. Same, but I apply the ruleset change myself with `gh api` after you confirm
X. Other (please specify)

[Answer]: A

### Question 3
How should the switch to lockfiles affect local setup? (`CLAUDE.md` currently says `pip install -r requirements.txt`.)

A. `requirements.txt` becomes the hash-pinned runtime lock (dashboard only), and `requirements-dev.txt` becomes the full dev and test lock. Local setup and `CLAUDE.md` change to `pip install --require-hashes -r requirements-dev.txt`, and `.venv` is reinstalled from it once
B. Keep `requirements.txt` as the dev install; name the runtime lock `requirements-runtime.txt` and point Streamlit Cloud at it
X. Other (please specify)

[Answer]: A

---

## Consolidated Summary Confirmation

**Mode:** guided

- **Scope:** this stage writes only the CI workflow, its gate scripts and their tests, the lockfiles and the CI config files. The application changes go to a separate follow-up piece of work, and the Cloud apps aren't created until it lands.
- **Burned-secret check:** added now, with one temporary, documented exclusion for `mock_hsm/auth.py`. A CI test fails if the exclusion outlives the literal, and the follow-up removes both (Q1: A).
- **Landing:** a PR from a `ci-pipeline` branch, merged when green. You then retarget the `main_branch_protection` ruleset to `main`, with the new required checks and squash-only merging, from a checklist I provide. I don't change repository settings (Q2: A).
- **Lockfiles:** `requirements.txt` becomes the hash-pinned runtime lock (dashboard only), and `requirements-dev.txt` the full dev and test lock. `CLAUDE.md` and `.venv` switch to the dev lock (Q3: A).

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
