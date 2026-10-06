# Security Requirements — U3 sign-in-gate

## Sources

- `inception/requirements-analysis/requirements.md` FR2.1, FR4.1–FR4.10, NFR1, NFR3, NFR4, NFR5, NFR7
- `construction/sign-in-gate/functional-design/rules.md` (BR1.1–BR7.1), `functional-spec.md` (W0–W5) and `entities.md`
- `inception/contract-design/contract-summary.md` C1, C4, C6, C7
- `nfr-requirements-questions.md` Q1–Q3; `memory/team.md` Deployment and Testing Posture; `memory/project.md` Forbidden (no exposure without a sign-in layer) and Corrections (a way out on every refusal screen; a neutral screen for system refusals)

## Threat Model (STRIDE, scoped to U3)

| Asset or flow | Threat | Mitigation (requirement) |
|---------------|--------|--------------------------|
| The dashboard's screens and its backend | Spoofing / elevation of privilege: a visitor who isn't allowed reaches tabs, the persona picker or the backend | NFR1.21, NFR1.22, NFR1.23 |
| The identity provider's `email_verified` claim | Spoofing: an unverified or string-valued claim treated as verified | NFR1.22 |
| The allowlist | Elevation of privilege through a wildcard or domain match, or a malformed list that fails open | NFR1.22, NFR1.24 |
| Missing or broken sign-in settings, or a gate exception | Fail-open into the persona picker | NFR1.24 |
| The signing secret and the sign-in cookie secret | Key reuse (one value signs both persona tokens and sign-in cookies) | NFR1.25 |
| Logs and screens | Information disclosure (emails, secret values, allowlist content, technical causes) | NFR1.26, NFR4.11 |
| The email shown on Screens 2, 3 and 4 | Tampering: markup in a provider-supplied email rendered as HTML or Markdown | NFR1.27 |
| A shared browser tab | Elevation of privilege: the previous account's persona survives into the next account | NFR1.28 |
| Sign-in callback and session cookie | Spoofing via a forged callback or cookie | Accepted, delegated to Streamlit's `st.login` (OpenID Connect authorisation-code flow with its own cookie signing); NFR1.25 keeps its key separate |
| The new runtime dependency (Authlib) | Supply-chain compromise | NFR7.11 |
| Repeated refusals | Denial of service by log flooding | NFR4.11 |

## Requirements

| ID | Requirement | Pass condition | Source |
|----|-------------|----------------|--------|
| NFR1.21 | Nothing but the page header and the gate's own screen renders until the gate allows. No tab, persona picker, site picker, banner, backend start or backend call happens for a refused visitor | AppTest checks, for each refusal path (signed out, not verified, not listed, settings missing, allowlist invalid, gate error): the render tree holds no tabs and no persona or site widgets, and the embedded backend's start function was never called | FR4.1, BR4.1 |
| NFR1.22 | A visitor gets in only when signed in with a non-blank email, `email_verified` is exactly the boolean `true`, and the trimmed, lower-cased email exactly equals an allowlist entry. No wildcard or domain match is interpreted | Unit tests of the pure decision function: allow; `email_verified` false, missing, null, `"true"` and `"false"`; not listed; a domain-only entry; mixed case and surrounding spaces allowed; signed in with no email refused as `gate_error` | FR4.3, FR4.4, BR2.3, BR3.2–BR3.4 |
| NFR1.23 | The decision is a pure function, unit-tested without Streamlit; the identity seam is the only code that calls Streamlit's sign-in API, and holds nothing else | An AST test asserts `decide` and `parse_allowlist` call no Streamlit API; a test asserts the only Streamlit auth calls (`login`, `logout`, the user object) in `dashboard/` are inside the seam | FR4.6, BR3.5, BR7.1 |
| NFR1.24 | The gate fails closed. A missing or short signing secret, any of the five sign-in keys missing or blank, an unreadable secrets file, an allowlist that is not a non-empty list of non-blank strings, and any exception inside the gate all show Screen 5 and never the persona picker | Tests for each case show Screen 5 and NFR1.21's render-tree assertions; a test that makes the identity read raise shows Screen 5 without Sign out | FR4.5, BR1.2, BR1.5, BR2.1, BR2.2, BR3.7, BR4.3 |
| NFR1.25 | The signing secret must differ from the sign-in cookie secret; equal values fail closed. The hosted signing secret is copied into the environment only when it is not already set there | Tests: equal values give Screen 5 and a log naming both settings but neither value; an exported value is not overwritten by the hosted one; a hosted value is copied when the environment lacks it, and a token then mints and verifies | FR2.1, team.md Deployment, BR1.1, BR1.3 |
| NFR1.26 | No email, secret value, sign-in setting value or allowlist entry appears in any log line or error message from this unit. On screens, no secret value, setting name or value, allowlist entry, refusal reason or technical cause is ever shown. The visitor's own email is shown only where the design puts it: "Signed in as:" on Screen 2, and the Account section on Screens 3 and 4, always as literal text (NFR1.27) | Captured-log tests for every refusal reason and for sign-out assert the email, the secret values and the allowlist entries are absent; screen tests assert Screen 2 and Screen 5 copy is exactly the mockup copy (Screen 2 including the visitor's own email), and that no screen contains a secret value, a setting name, an allowlist entry or a reason | NFR1, FR4.8, FR4.10, BR4.2, BR6.1, BR6.3 |
| NFR1.27 | The email is shown only as literal text: Markdown or HTML in it is never interpreted | A test signs in with an email containing Markdown and HTML (for example `<b>x</b>@example.com` and `*a*@example.com`) and asserts the rendered element holds the literal string and no markup element | AC4.3.3, BR4.2 |
| NFR1.28 | Sign-out ends the persona's backend session (best effort), clears every dashboard key of the browser session, then signs out of Google. A different allowed account on the same tab never inherits the previous account's persona, even without Sign out | AppTest with the seam patched: after Sign out, the session state holds no persona login, notice or scoped item, and a backend session-end request was sent; a backend failure during sign-out still completes it; an allowed rerun with a different email than the bound one clears the persona before rendering | AC4.6.2, AC4.6.3, BR5.1, BR5.2 |
| NFR4.11 | Each refusal is logged once per browser session per reason, with the reason and no identity data: `not_verified` and `not_listed` at INFO, `settings_missing`, `allowlist_invalid` and `gate_error` at WARNING (the gate error line adds the exception type only). `not_signed_in` is not logged | Captured-log tests: one line per reason across repeated reruns in one session; the expected level per reason; no line for a signed-out visitor; a new line after Sign out and a new refusal | FR4.10, NFR4, BR6.1, BR6.2, Q3 |
| NFR5.11 | Screens 1, 2 and 5 have exactly one h1 (the shared page header), state their message in text, and offer a standard button reachable with Tab and activated with Enter | AppTest asserts one h1 and the exact copy per screen; the keyboard check runs in U5's browser tests | NFR5, AC4.1.4, AC4.1.5, BR4.4 |
| NFR7.11 | The sign-in dependency arrives only as `streamlit[auth]==1.64.0` in `requirements.in`, with the runtime lock recompiled by the command at the top of the file and hash-pinned; it passes `pip-audit` with no new exception | Both locks (`requirements.txt` and `requirements-dev.txt`, which includes the runtime lock) are recompiled with the commands at the top of their `.in` files and committed in the same change; `requirements.txt` holds `authlib` with hashes; `lock-check`, `audit` and both `tests` legs (Python 3.10 and 3.14) are green on the pull request, which proves Authlib resolves and installs on both | NFR7, FR8.1, AC8.1.1, Q2 |

## Assumptions & Open Questions

- [assumption] Google reports `email_verified` as a boolean through Streamlit's user object (feasibility risk R1). If it doesn't, NFR1.22 refuses every visitor as `not_verified`, which is the fail-closed outcome. Code Generation confirms this with a real local sign-in.
- [assumption] Streamlit's own sign-in cookie lifetime and callback handling are accepted as they ship in 1.64.0. This unit doesn't configure them beyond the C7 keys.
