# Security Design — U3 sign-in-gate

## Sources

- `nfr-requirements/security-requirements.md` NFR1.21–NFR1.28, NFR4.11, NFR7.11 and its STRIDE threat model
- `nfr-requirements/tech-stack-decisions.md` (seam, modules, logger, `streamlit[auth]==1.64.0`)
- `functional-design/functional-spec.md` W1–W5, Error Handling; `functional-design/rules.md` BR1.1–BR7.1
- `inception/contract-design/contract-summary.md` C1 (TokenAuth), C4 (SignInGate API), C6 (markers), C7 (hosted secrets schema)
- `nfr-design-questions.md` Q1 A (one error boundary), Q2 A (one shared test helper); summary confirmed
- `memory/team.md` Code Style (broad `except` only at a visible-state boundary with `# noqa: BLE001 -- <reason>`) and Deployment (sign-in gate rules); `memory/project.md` Corrections (a way out on every refusal screen; a neutral screen for system refusals)

## Design Decisions

### S1 — Nothing renders before the gate allows (NFR1.21)

- `dashboard/app.py` calls `auth_gate.gate()` straight after the page header, and before anything else: the embedded backend start (U2), tabs, persona picker, site picker and the banner and caption slots (U4). If `gate().outcome != "allow"`, the app calls `st.stop()`. This is C4's caller rule, and it is the only branch in `app.py` that the gate adds.
- `gate()` renders only its own screen container, so a refused rerun's render tree holds the h1, one gate screen and at most one button.
- **Tests:** for each of the six refusal paths (signed out, not verified, not listed, settings missing, allowlist invalid, gate error), an `AppTest` built with the shared helper (Q2 A) asserts that the render tree has no tabs and no persona or site widgets, and that a spy on `embedded.start` was never called.

### S2 — A pure decision behind a thin seam (NFR1.22, NFR1.23)

- `decide(identity, allowlist)` and `parse_allowlist(raw)` are plain functions with no Streamlit import in their bodies. The checks run in the order fixed by BR3.1–BR3.4:

  ```
  decide(identity, allowlist):
      if not identity.signed_in:          return refuse_visitor / not_signed_in
      email = (identity.email or "").strip().lower()
      if not email:                       return refuse_unavailable / gate_error
      if identity.email_verified is not True: return refuse_visitor / not_verified
      if email not in allowlist:          return refuse_visitor / not_listed
      return allow / ok
  ```

- `is not True` is an identity check, so `"true"`, `1`, `None` and a missing claim all refuse. Allowlist entries are compared as exact strings. No `*`, `@domain` or suffix rule exists, so a domain-only entry such as `example.com` never matches a full address.
- **The seam** is three functions in `auth_gate`: `current_identity()`, `sign_in()` and `sign_out()`. They are the only code in `dashboard/` that touches `st.user`, `st.login` or `st.logout`. Each one only wraps the Streamlit call. `current_identity()` copies `is_logged_in`, `email` and `email_verified` into an `Identity` and passes the raw verified value through unchanged.
- **Tests:** unit tests of `decide` for every case in NFR1.22. An AST test asserts `decide` and `parse_allowlist` call no `st.` attribute. A scan of `dashboard/` asserts that `st.user`, `st.login` and `st.logout` appear only inside the three seam functions.

### S3 — Fail closed with one error boundary (NFR1.24, Q1 A)

The expected failures are decided by specific checks, and each one returns a `refuse_unavailable` decision without raising:
- the signing secret: `require_secret()` raises `SecretMissingError` (C1), which the check catches by name and maps to `settings_missing`;
- the secret equals `cookie_secret`: `settings_missing`;
- a missing or blank key among the five sign-in keys, or a missing `[auth]` or `[auth.google]` section (C7): `settings_missing`;
- `parse_allowlist` raises `AllowlistInvalidError`, which is caught by name and mapped to `allowlist_invalid`.

Anything else is unexpected, and one boundary in `gate()` catches it:

```
def gate():
    render_page_header()                  # outside the boundary: it must run first and once (BR4.4)
    try:
        decision = _evaluate()            # bridge, secret, settings, allowlist, identity, decide
        _log_refusal_once(decision)
        _render_screen(decision)          # Screen 1, 2 or 5, or nothing on allow
        return decision
    except Exception as exc:  # noqa: BLE001 -- any gate failure must become Screen 5, never the persona picker
        decision = Decision("refuse_unavailable", "gate_error")
        _log_refusal_once(decision, error_type=type(exc).__name__)
        _render_unavailable()             # Screen 5
        return decision
```

- `_render_unavailable()` reads the identity in its own guarded call (BR4.3). That call is the only other broad catch in the module. If it fails, Screen 5 shows no Sign out button, and "Reload the page or try again later." is the way out (project.md correction: a way out on every refusal screen).
- `_render_unavailable()` uses only fixed copy and the markers module, so an error inside it is very unlikely. If it raises anyway, the exception propagates to Streamlit's own error display. That still never reaches the persona picker, because `app.py` calls `st.stop()` unless the outcome is `allow`, and an exception means no `allow` was returned.
- `st.stop()` and Streamlit's rerun signal raise `StopException` and `RerunException`, which derive from `BaseException`, not `Exception`, in Streamlit 1.64.0 (checked against the installed package), so the boundary doesn't swallow them. A test pins this, so a Streamlit upgrade that changes it fails the suite instead of turning a sign-in redirect into Screen 5.
- **Tests:** one test per failure case in NFR1.24 shows Screen 5 and repeats S1's render-tree assertions. A test makes `current_identity()` raise and asserts Screen 5 without Sign out. A test makes `decide` raise and asserts Screen 5 and a `gate_error` log line naming only the exception type.

### S4 — Separate secrets, copied only when unset (NFR1.25)

- `dashboard/secrets_bridge.py` exposes `bridge_signing_secret()`. It reads `st.secrets` in a guarded call: if the secrets can't be read, every hosted key counts as absent (BR1.5). If `HSM_SIGNING_SECRET` is unset or empty in `os.environ` and the hosted mapping has it, the bridge copies it in. An exported value is never overwritten.
- After the bridge, the gate runs `require_secret()` and then compares the signing secret with `auth.cookie_secret`, when one is set, using `hmac.compare_digest` on UTF-8 bytes. Equal values give `settings_missing`, and the log line names both settings and neither value.
- The bridge stays in `dashboard/`, so `mock_hsm/auth.py` keeps only standard-library imports (team.md Code Style; project.md correction).
- **Tests:** equal values give Screen 5 and a log line that holds neither value; an exported value survives a different hosted one; a hosted value is copied when the environment lacks it, and `mint_token` and `verify_token` then round-trip.

### S5 — No disclosure, and the email shown as literal text (NFR1.26, NFR1.27)

- **Logs:** every refusal line is built only from constants: the reason, plus the exception type name for `gate_error` and the setting names for `settings_missing`. No log call in `auth_gate.py` or `secrets_bridge.py` takes an email, a secret, a setting value, an allowlist entry or an exception message. The backend session-end failure at sign-out logs the error type without the session id.
- **Screens:** the copy for Screens 1, 2 and 5 is fixed text held as module constants that match the mockups exactly. The only variable value on any gate screen is the visitor's own email, shown on Screen 2 and in the Account section on Screens 3 and 4.
- **Literal email:** the email goes through the existing `dashboard.safe_text.escape_md` before it reaches a Markdown-capable element. That helper already backslash-escapes every Markdown and HTML control character (U4 of the dashboard-writes work), so `<b>x</b>@example.com` and `*a*@example.com` are shown as typed.
- **Tests:** captured-log tests for every refusal reason and for sign-out assert that the email, both secret values and the allowlist entries are absent. Screen tests assert that the Screen 2 and Screen 5 copy matches the mockups exactly and that no screen holds a secret value, a setting name, an allowlist entry or a reason. A rendering test signs in with the two markup emails above and asserts that the rendered value holds the literal string and no markup element.

### S6 — Sign-out and the account binding (NFR1.28)

- `end_visitor_session()` is a plain function in `auth_gate`, outside the seam, so a test that patches the seam still runs it (BR7.1). It does two things:
  1. If a persona login holds a backend session, it calls the backend's session-end route through the existing client. It swallows only `mock_hsm.embedded.BackendNotRunning` and `agents.hsm_client.HsmApiError` (which covers its subclass `HsmUnavailable`), each by name, and logs the type without the session id.
  2. It removes every dashboard key from the session state: the persona login and notice, every key in `session.SCOPED_DEFAULTS`, every record-form widget key (prefix `session.FORM_KEY_PREFIX`), the refusal log marks and the account binding. The key list comes from `session.py`, so a scoped item added later is cleared without editing the gate.
- The Sign out button calls `end_visitor_session()` and then `sign_out()`. If `sign_out()` raises, the state has already been cleared, and the error is logged as `gate_error`.
- **Account binding:** on `allow`, the gate compares the session's bound email with the identity's email. If they differ, it runs `end_visitor_session()` and binds the new email before DashboardShell renders (BR5.2). This also covers a Google session that expired without Sign out.
- **Tests:** after Sign out, the session state holds no persona login, notice or scoped item, and a spy recorded the session-end request; a backend failure during sign-out still completes it; an allowed rerun with a different email clears the persona before anything renders.

### S7 — Refusal logging without flooding (NFR4.11)

- Logger `dashboard.auth_gate`. `not_verified` and `not_listed` are logged at INFO, and `settings_missing`, `allowlist_invalid` and `gate_error` at WARNING. `not_signed_in` is never logged.
- The session state holds a set of reasons already logged in this browser session. `_log_refusal_once` writes a line only when the reason is new, then adds it to the set. `end_visitor_session()` clears the set, so a refusal after Sign out is logged again.
- This bounds the log to at most five lines per browser session, whatever the number of reruns, which addresses the log-flooding threat in the requirements' threat model.

### S8 — The sign-in dependency (NFR7.11)

- `requirements.in` changes `streamlit==1.64.0` to `streamlit[auth]==1.64.0`. Both locks are recompiled with the `uv pip compile` commands at the top of their `.in` files and committed in the same change. The runtime lock then pins Authlib and its dependencies with hashes.
- `pip-audit` runs through the existing `audit` job with no new `security-exceptions.toml` entry. `lock-check` and both `tests` legs prove the lock resolves and installs on Python 3.10 and 3.14.

## Residual Risks (accepted)

| Risk | Why accepted | Owner of the control |
|------|--------------|----------------------|
| A forged sign-in callback or session cookie | Delegated to Streamlit's OpenID Connect flow and its own cookie signing. S4 keeps the cookie key separate from the token key | Streamlit `st.login` |
| Google reports `email_verified` in another type | `is not True` refuses every visitor, which fails closed. Code Generation confirms the type with a real local sign-in | U3 Code Generation |
| Anyone on the allowlist can pick any persona | Accepted for a demo (team.md Deployment) | Repository owner |

## Assumptions & Open Questions

- [assumption] In Streamlit 1.64.0, `st.user` exposes `is_logged_in`, and the OpenID claims `email` and `email_verified` read as attributes or keys. The seam is the only place that depends on this, so a different shape changes one function.
- [assumption] A later Streamlit release keeps `StopException` and `RerunException` outside `Exception`. S3's test fails the suite if an upgrade changes this.
