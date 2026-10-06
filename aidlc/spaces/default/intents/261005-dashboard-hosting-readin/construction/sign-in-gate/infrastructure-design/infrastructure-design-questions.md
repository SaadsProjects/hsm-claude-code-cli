# Infrastructure Design Questions — U3 sign-in-gate

Most of the infrastructure is already decided:
- The host is Streamlit Community Cloud, one process per app (team.md Deployment).
- Sign-in uses Streamlit's built-in Google sign-in. U3 adds no service, database, queue or cloud resource.
- The hosted secrets follow contract C7. A committed `.streamlit/secrets.toml.example` holds placeholders only, and the real values are entered in U6.
- `.streamlit/secrets.toml` and `.env.local` are already git-ignored.

Two points are still open.

## Q1 — Where does a local `streamlit run` get the signing secret?

Today the local dashboard doesn't read `.env.local`, so the developer exports the secret first (CLAUDE.md). The secrets bridge runs before the gate on every rerun.

A. The bridge loads the secret in this order: an exported `HSM_SIGNING_SECRET` first, then the hosted secrets, then `.env.local` through the existing `mock_hsm.auth.load_local_secret`. A hosted app has no `.env.local`, so that last step only matters locally. The export step leaves CLAUDE.md (Recommended)
B. Keep it as it is: the bridge reads only the environment and the hosted secrets, and local runs still need the export
X. Other (please specify)

[Answer]: A

## Q2 — Does U3 change the CI pipeline?

U3's tests run in the existing `tests (3.10)`, `tests (3.14)` and `coverage-gate` jobs. U3 also changes the two lockfiles, so `lock-check` and `audit` check them. U3 touches `dashboard/auth_gate.py` and `dashboard/markers.py`, which are on the `browser-tests` watch list. That job then runs `pytest -m browser`, finds no browser test yet, and passes on "no tests ran".

A. No CI change. Extending the watch list (to `requirements-dev.txt` and `.github/workflows/ci.yml`) and adding the browser test, the meta-test and the retry stay with U5, as planned (Recommended)
B. Extend the `browser-tests` watch list in U3 already
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- **Local signing secret (Q1 A):** the secrets bridge takes `HSM_SIGNING_SECRET` from the first source that has it:
  1. an exported value, which always wins;
  2. the hosted secrets, copied only when the environment lacks the variable or it is empty;
  3. `.env.local`, through the existing `mock_hsm.auth.load_local_secret`, which reads only that one line and never overrides a variable that is present.

  The file is read at most once per process, because the variable is set afterwards. A hosted app has no `.env.local`. An unreadable file is an unexpected error, so it becomes Screen 5 through the gate's boundary. CLAUDE.md drops the export instruction for the local dashboard.
- **CI (Q2 A):** no change to jobs, steps, permissions or required checks. U3's tests run in `tests (3.10)`, `tests (3.14)` and `coverage-gate`, and the lockfile change is checked by `lock-check` and `audit`. `browser-tests` runs because `auth_gate.py` and `markers.py` change, and it passes on "no tests ran" until U5 adds the first browser test, extends the watch list and adds the meta-test and the retry.
- **Fixed by earlier decisions:**
  - one Streamlit Community Cloud process per app;
  - Google sign-in through Streamlit, with no new service or cloud resource;
  - hosted secrets per C7, entered by the owner in U6;
  - a committed `.streamlit/secrets.toml.example` with placeholders only. A local run copies it to the git-ignored `.streamlit/secrets.toml`. With placeholder values the local dashboard shows the sign-in screen, which is the local slice. A real local sign-in needs a local OAuth client with `http://localhost:8501/oauth2callback` as its redirect;
  - the app log is the only monitoring surface. The refusal lines are its signals, and the post-deploy check (U5) is the deployment health signal.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
