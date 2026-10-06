**Collaborator:** aidlc-developer-agent

## Contribution

Focus: whether each story can be built and tested as written against the code at `825a0f8`, whether the stories are small and independent, whether the dependencies are right, and what must ship together in the first pull request (requirements finding R-01). I read the code to check this. I did not run anything: the delegated-agent guard blocks dynamic commands.

### 1. What the current code shows

| Area | What the code does today | What that means for the stories |
|---|---|---|
| `st.user` under `AppTest` | Streamlit 1.64's `testing/v1/local_script_runner.py` hard-codes `user_info={"email": "test@example.com"}` with no `is_logged_in`. `user_info._get_user_info()` adds `is_logged_in=False` only when an `[auth]` secrets section exists. `AppTest` has no public way to set a signed-in identity. | You can't fake a signed-in identity through `AppTest` itself. US4.1–US4.4, US4.6, US5.1, US6.1 and US3.3 need a thin seam in `dashboard/auth_gate.py`: a `current_identity()` that wraps `st.user`, and `sign_in()` / `sign_out()` that wrap `st.login("google")` / `st.logout()`. Tests monkeypatch the seam, which works because `AppTest` runs in-process. `tests/test_dashboard_app.py` already does this with `session.client_for`. "Fake identity" in the ACs should mean this seam. |
| `st.login` in `AppTest` | Without a complete `[auth]` section, `st.login` raises `StreamlitAuthError`. Even with one, it only sends a redirect. | AC4.6.2 (Sign out → sign-in screen) can only be tested through the patched `sign_out()` seam clearing the fake identity. AC4.2.2 ("Google is the configured provider") can't be checked against the app's settings: `.streamlit/secrets.toml` is git-ignored (F2), so the repository never holds them. It can be checked by asserting that the seam calls `st.login("google")`, and that a committed `.streamlit/secrets.toml.example` (not ignored, no values) has an `[auth.google]` section. |
| Base URL of the client | `agents/hsm_client.py` reads `HSM_BASE_URL` into a module constant at import, and `HsmClient.__init__(..., base_url=HSM_BASE_URL)` binds it as a default argument. `dashboard/session.client_for` calls `HsmClient(mint_token(user_id))` with no `base_url`. | FR3.3's first option ("set `HSM_BASE_URL` before the client is first imported") won't work in-process: `app.py` imports `agents.hsm_client` before any backend could start, and on reruns the module is already cached. The in-process start has to return its actual address, and `session.client_for` has to pass it as `base_url`. AC3.1.2 should state this. The caption at `app.py:483` and the `URLError` message at `app.py:510` (which also says "Start it with `python3 -m mock_hsm.server &`") both use the import-time constant. Both must change for US3.1, and AC3.3.2 forbids showing the address. |
| In-process start | `mock_hsm/server.run()` calls `audit.configure()` and then `serve_forever()`, which blocks. | You need a new standard-library function in `mock_hsm/`, for example `start_in_process() -> base_url`. It binds `127.0.0.1:0`, runs `serve_forever` on a daemon thread, and keeps a module-level singleton behind a `threading.Lock`. A module-level singleton survives Streamlit reruns and `AppTest` runs because `sys.modules` persists, so AC3.2.1 and AC3.2.2 are testable. They need a way to observe the server count, such as a `_server` attribute or a `running_backends()` helper, and the AC should name it. Port 0 also follows the team rule that new tests never add a fixed port. |
| Existing dashboard `AppTest`s | `test_dashboard_app.py` and `test_dashboard_data.py` point `session.client_for` at their own ephemeral server. | Once the gate and the in-process start are in place, every existing dashboard `AppTest` must (a) patch `current_identity()` to an allowed, verified email with a test allowlist and (b) either stop the in-process start or let it run once as the singleton. No story covers this. It is real work spread across a large share of the suite, so it should be an AC, not left implicit (see section 4). |
| Missing secret in the backend | `server.py:718–719` catches only `TokenError` around `verify_token`. | If the new missing- or short-secret error isn't a `TokenError`, it escapes the handler thread. `http.server` drops the connection, and the client sees `RemoteDisconnected`/`URLError`, not a clear status. Either the backend refuses to start without a valid secret (put this in `server.run()` / `__main__`, so the start script, `python3 -m mock_hsm.server` and the in-process start all get it), or the verify path turns the error into an explicit 5xx. US2.2 checks only the bash script. It should also cover `python3 -m mock_hsm.server`, because `scripts/start_mock_server.sh` just `exec`s it. |
| Publish hook | `require_no_violations.py` already wraps `main()` in a broad catch that turns any exception into a deny (`:87`), and `mint_token` is called inside `main()`. | AC2.3.1 is implementable and fails first today: with the literal in place, minting succeeds, so a "no secret ⇒ deny" test fails until the literal goes. After US1.2 the existing catch produces the deny, with the reason ".../`<ErrorType>`: …`HSM_SIGNING_SECRET`…". The test must delete `HSM_SIGNING_SECRET` from the subprocess `env` dict and keep `HSM_ACTIVE_USER` set, because the user check runs first. `test_hooks.py` builds `env={**os.environ, ...}`, so AC1.4.3 inheritance holds. The test runs in a few seconds and needs no backend. |
| MCP tools | `mcp_server/hsm_tools._client()` calls `mint_token` on every tool call, and FastMCP turns exceptions into tool errors. `.mcp.json` holds only `HSM_BASE_URL`. | AC2.4.1 is implementable. It needs its own test: a separate stdio subprocess with the secret removed from `env` and no backend. It shouldn't go into the single sequential `_run()` scenario in `test_mcp_tools.py`, where a failure would stop the whole scenario. "Any tool" should be tested as one parametrized loop over the existing `expected` tool set, or reworded to "every tool shares `_client()`, and one read tool and one write tool are tested". AC2.4.2 is already true today. Keep it as a regression check. |
| Burned-secret check | `TEMPORARY_EXCLUSIONS = ("mock_hsm/auth.py",)`. `PERMANENT_EXCLUSIONS` covers `.gitleaks.toml` and the AI-DLC record tree. | AC1.3.1 and AC1.3.2 are what `scripts/check_burned_secret.py` already enforces once the tuple is empty. AC1.3.2's "documented gitleaks allowlist" should read "`PERMANENT_EXCLUSIONS`", because the record tree is excluded as well (project correction: records are never rewritten). |
| `browser-tests` job | The watch regex at `ci.yml:241` doesn't include `requirements-dev.txt` or `ci.yml`. The job passes on exit 5 (`|| [ $? -eq 5 ]`). | AC8.3.1 and AC8.3.3 are concrete, small edits. AC8.3.3 has to land in the same pull request as the first `tests/test_*browser*.py`, or the job either keeps accepting "no tests ran" or fails with nothing to run. |

### 2. A conflict the stories carry forward: the build check can't see the build

US7.1 (AC7.1.1) and US9.1 (AC9.1.2) need the post-deploy check to confirm the build identifier. US7.3 and F1 forbid the check from ever signing in. But AC5.1.2 puts the build identifier only in the sidebar of an **allowed** visitor (wireframes Screen 3), and AC4.1.2 says the not-signed-in render tree has nothing but the title, the invitation line and "Sign in". Streamlit Community Cloud lets an app add no custom HTTP routes (only `/_stcore/health`), so there's no unauthenticated endpoint the check could read instead. As written, AC7.1.1 can't pass.

Smallest fix: show the build identifier as a small caption on the sign-in (and refusal) screen too, with its selector in `dashboard/markers.py`, and allow that one element in AC4.1.1/AC4.1.2. The repository is public, so exposing the commit SHA reveals nothing new. This changes FR5.2 and the wireframe, so the lead should raise it with the human rather than settle it here.

Related (R-04): AC9.1.2 takes "the `main` commit SHA" as the expected build. If Streamlit Cloud's checkout has no `.git`, the app shows a fingerprint (US5.2), and the SHA won't match. US5.2 needs an AC for a way to compute the expected value locally: `python -m agents.build_info` prints the identifier using the same function the app uses. The fingerprint's file set must leave out anything that differs between a clone and the host: `__pycache__`, `.env*`, `.streamlit/secrets.toml`, `.git`, `aidlc/`. Fix the set to tracked source under the shipped packages so AC5.2.1 and AC5.2.2 stay stable.

### 3. Gaps that make some ACs untestable or unclear

- **Who loads `.env.local`?** US2.1 writes it, and AC10.1.2 expects "the documented start command" to work from a fresh clone with it. Nothing reads it: neither Python nor Streamlit loads `.env.local` on its own. Add an AC to US2.2 that the start script sources `.env.local` when present, and say in US10.1 how the dashboard, the `claude` shell (for the MCP server and hook) and the separate backend all get the same value. If the backend and the MCP server end up with different secrets, every tool call fails with "bad signature", not the clear US2.4 message.
- **The refusal screen for "missing settings" or "gate error" has no email to show.** AC4.3.3 says every refusal shows "the signed-in email". When `[auth]` is missing (AC4.4.1) or the gate throws before an identity is read (AC4.4.2), there's no email. Say which screen shows then (the refusal screen without the email line is fine) and that "Sign out" or reload is still there.
- **"No backend call" in AC4.1.2** should be the observable "the in-process backend has not been started, and no HTTP request was made". With US3.1 the start is a side effect, so the gate must run before `start_in_process()`. That's a useful assertion against the US3.2 singleton (count = 0 before allow).
- **AC1.2.2 "31-byte secret"**: say whether that means bytes of UTF-8 or characters. Use bytes, to match the team rule.
- **AC1.4.2 "two test runs differ"** compares across separate pytest processes, which is awkward to automate. Reword: the generator function in `conftest.py` returns a different value on two calls, and no fixed secret is in `tests/`. This keeps the intent.
- **AC8.3.4** is a process rule (M2) with no rename planned in this intent. It can't fail in this work. Keep it as a checklist note rather than an AC, or make it concrete: "the job names in `ci.yml` still equal the ruleset's 10 required checks", checked by `check_workflows.py`.
- **AC2.5.2** ("the log names the missing setting") is testable with `caplog` under `AppTest` because it runs in-process. The secrets bridge must log through the standard `logging` module, not `st.error`.

### 4. Sizing and independence

- Most stories are the right size: one behaviour, one test file or less. US1.1, US1.2, US1.4, US2.3, US2.4, US2.6, US4.5, US4.7, US5.2, US8.1 and US8.4 are each well under a day and independent.
- **US4.1 is under-sized.** Once the gate sits in front of `main()`, every existing dashboard `AppTest` must go through it with a fake allowed identity. Add an AC: "Given the existing dashboard `AppTest` suite, when it runs through the gate with a fake allowed identity fixture, then it passes unchanged in count." Or add a small separate story, US4.8, for the shared fixture. Without it, the floor in `.test-floor` is at risk.
- **US3.1 is under-sized** for the same reason. The in-process start changes `session.client_for` (adds `base_url`), the backend caption and the `URLError` path. Those belong in its ACs.
- **US7.1 is the largest story.** It needs Playwright, a Streamlit server started on loopback in the test (a subprocess on a free port), a temporary `.streamlit/secrets.toml` with a dummy `[auth]` section so the sign-in screen renders (no real IdP is contacted, because the check never clicks "Sign in"), and `markers.py`. The browser tests for US7.1 and US7.2 don't need a full fake OIDC provider. A dummy `[auth]` config is enough, because nothing signs in. "Fake identity provider" in AC7.1.1 and AC8.2.2 should say that.
- **AC7.2.2** (an app without the gate) needs a tiny throwaway Streamlit script under `tests/` that renders tabs. Its name must match `tests/*browser*` or be on the watch list, or the AC8.3.2 meta-test will flag it.
- **US9.1** is a manual console action plus a check run. It's correctly kept separate, and its evidence (AC9.1.2) is fine once section 2 is fixed.

### 5. Dependency corrections

- US1.3 depends on US2.3 and US2.4 as well, not only US1.1, US1.2 and US1.4. The literal can't be removed until the hook and the MCP tools are proven to fail closed (R-01). It also depends on US2.1 and US2.6, because local development has no working path until the dev-secret script and the ignore lines exist.
- US2.1 → US2.6 is right.
- US2.2 depends on US1.2 **and** on the backend refusing in `server.run()` (section 1). Making `server.run()` refuse is part of US2.2, not of US3.
- US3.3 → US4.6 is right. US3.1 should add a dependency on US4.5/US4.1 (the gate runs before the start), not only on US1.1.
- US5.1 → US4.2 becomes "US5.1 → US4.1 (sign-in screen) and US4.2" if section 2 is accepted.
- US6.1 → US4.2 is right.
- US7.1 → US8.1 is missing (Playwright must be in the dev lock first).
- US8.2 → US7.1, not the other way round. The browser job has nothing real to run until the first browser test exists. US8.3 AC8.3.3 lands together with US7.1.
- US2.5 doesn't depend on US4: the bridge can land before the gate. It only has to be in place before any hosted app exists (US9.1).

### 6. What the first pull request must contain so that removing the fallback leaves no ungated entry point (R-01)

The first pull request must hold everything that has to fail closed the moment the literal disappears. Everything else can wait for the final pull request:

| Story | Why it must be in pull request 1 |
|---|---|
| US1.1, US1.2 | The read-at-call-time and refuse-missing/short behaviour is the change itself. |
| US1.4 | Without the conftest secret, the whole suite (including the subprocess tests) fails, and CI can't go green. |
| US1.3 | The literal and exclusion removal (M1), with its regression tests in the same commit. |
| US2.3 | The hook is the dangerous entry point: a crash fails open. Its deny-without-secret test proves the fail-closed path before the literal goes. |
| US2.4 | The MCP tools must report the missing secret clearly. Without this, local tooling breaks silently. |
| US2.2 (including the `server.run()` refusal) | Otherwise the separate backend starts and then drops every connection on verify (section 1). |
| US2.1, US2.6 | Local development has no other way to get a secret, and the new `.env.local` must already be ignored when it's written. |
| US10.1 (secret-setup part only) | AC10.1.3 requires the docs to ship with the change, and a fresh clone can't start without them. |

US8.4 (the two `noqa` reasons) touches `require_no_violations.py`, which US2.3 already edits. It's cheap to include and avoids a second edit to the same file, but it's optional.

Not needed in pull request 1:
- US2.5 (no hosted app exists, and the dashboard runs only on loopback).
- US3 and US4. Locally, the persona-picker dashboard stays on loopback, which `project.md` Forbidden allows.
- US5–US8 except US8.4.

Consequence for the walking skeleton: pull request 1 alone can't show "the dashboard starts locally with its in-process backend and shows the sign-in screen", because that needs US3.1 and US4.1. This is the contradiction R-01 already raised. The stories don't resolve it. The lead should state, here or in Units Generation, that the skeleton is pull request 1 merged green **plus** US3.1 and US4.1 working locally on the intent branch. The other option is to restate the skeleton as "the dashboard refuses to start without a secret".

## Positions

- AGREE: Stories at one behaviour each (Q4 A) fit the TDD posture; US1.1, US1.2, US1.4, US2.3, US2.4, US4.5, US4.7 and US5.2 can each be built test-first as written.
- AGREE: AC2.3.1 (the hook denies without a secret, test first) is implementable: the test fails today because the literal still mints, and passes through the existing `__main__` catch once US1.2 lands.
- AGREE: AC3.2.1 and AC3.2.2 (single backend) are testable with a module-level, lock-guarded singleton in `mock_hsm/`, because `sys.modules` persists across `AppTest` runs and Streamlit reruns.
- AGREE: US4.5 as a pure decision function with the Streamlit calls kept thin matches team.md Code Style and is the seam that makes US4.1–US4.4 testable.
- OBJECT: AC7.1.1 and AC9.1.2 can't pass while AC5.1.2 and AC4.1.1/AC4.1.2 keep the build identifier off the not-signed-in screen, because the check may never sign in (F1); show the build caption on the sign-in screen too, with a `markers.py` selector, and raise the wireframe change with the human.
- OBJECT: AC4.1.1, AC4.6.2 and "fake identity" throughout US4 assume `AppTest` can set a signed-in user; Streamlit 1.64's `AppTest` hard-codes `user_info` and has no setter, so the ACs should name the patched `current_identity()` / `sign_in()` / `sign_out()` seam in `dashboard/auth_gate.py`.
- OBJECT: AC4.2.2 checks "the app's sign-in settings", which are git-ignored (F2) and never in the repository; reword to "the sign-in seam calls `st.login("google")`" plus a committed `.streamlit/secrets.toml.example` with `[auth.google]`.
- OBJECT: AC3.1.2 / FR3.3 setting `HSM_BASE_URL` before import isn't workable in-process (`agents/hsm_client.py` binds it at import and as a default argument); the AC should require `session.client_for` to pass the start function's returned address as `base_url`.
- OBJECT: US1.3's dependencies omit US2.1, US2.3, US2.4 and US2.6; per R-01, the literal may only go once every entry point fails closed and local development has a secret path, so those stories ship in pull request 1 with US1.1–US1.4, US2.2 and the secret-setup part of US10.1.
- OBJECT: US2.2 covers only the bash script; `server.run()` (and `python3 -m mock_hsm.server`) must refuse without a valid secret, or `server.py:718` lets the new error escape and drop connections; add that AC.
- OBJECT: No story or AC loads `.env.local`, yet AC10.1.2 depends on it; add an AC to US2.2 (the start script sources `.env.local` when present) and say in US10.1 how the `claude` shell gets the same value.
- OBJECT: US4.1 and US3.1 leave out moving the existing dashboard `AppTest` suite through the gate and the in-process start; add an AC (or a story, US4.8) for a shared fake-allowed-identity fixture so `.test-floor` holds.
- OBJECT: AC4.3.3 requires the signed-in email on every refusal, but the missing-settings and gate-error refusals (AC4.4.1, AC4.4.2) have no email; say what those screens show, keeping "Sign out" or reload.
- OBJECT: US5.2 has no way to learn the expected fingerprint for AC9.1.2 / R-04; add an AC that `python -m agents.build_info` prints the identifier with the same function and a fixed file set.
- OBJECT: US8.2 should depend on US7.1 (and US7.1 on US8.1), not the reverse; AC8.3.3 must land in the same pull request as the first browser test.
- OBJECT: AC1.4.2 (two separate test runs differ) and AC8.3.4 (a rename that isn't planned) can't fail as written; reword AC1.4.2 to two calls of the generator, and make AC8.3.4 a `check_workflows.py` assertion or move it to a checklist.
