# NFR Requirements Questions — U3 sign-in-gate

Most NFR targets for this unit follow directly from the inception NFRs and the approved functional design:

- **NFR1:**
  - fail closed on any secret, settings, allowlist or gate error;
  - no secret, setting value or email in any log or screen.
- **NFR3:** test-first, with both floors held. The sign-in wiring is covered through the seam, because browser tests don't count toward coverage.
- **NFR4:** one refusal line per reason per browser session.
- **NFR5:** one h1, text-only messages and keyboard-reachable buttons.
- **NFR7:** the new dependency arrives only through the hash-pinned lock and passes `pip-audit`.

These questions set what is still open.

## Q1 — How much time may the gate add to each page interaction?

Streamlit re-runs the whole page on every click, and the gate runs first each time:
- it reads the secrets;
- it checks the settings;
- it parses the allowlist;
- it reads the identity;
- it decides.

NFR2 gives the whole dashboard 30 seconds from the staging app waking up.

A. At most 50 ms for the gate's own work per rerun (excluding Google's sign-in round trip), checked by a `perf`-marked test that runs by hand, not in CI (Recommended)
B. At most 200 ms, checked the same way
C. No separate budget; only the 30-second whole-app target applies
X. Other (please specify)

[Answer]: A

## Q2 — How is the new sign-in library (Authlib) pinned?

`st.login` needs Authlib, which `streamlit[auth]` brings in. The runtime lock is hash-pinned and recompiled from `requirements.in`.

A. Add only `streamlit[auth]==1.64.0` to `requirements.in` and let the lock pin whatever Authlib version that extra resolves to (Recommended)
B. Also add an explicit lower bound for Authlib in `requirements.in` (for example `Authlib>=1.3.2`)
X. Other (please specify)

[Answer]: A

## Q3 — At what log level are refusals written?

Visitor refusals (not verified, not on the allowlist) are expected behaviour. Settings and gate errors mean the app is misconfigured.

A. Visitor refusals at INFO; `settings_missing`, `allowlist_invalid` and `gate_error` at WARNING (Recommended)
B. Every refusal at WARNING
C. Every refusal at INFO
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- **Gate time (Q1 A):** the gate's own work adds at most 50 ms per rerun, not counting Google's sign-in round trip. A `perf`-marked test checks this by hand; it never runs in CI.
- **Authlib (Q2 A):** add only `streamlit[auth]==1.64.0` to `requirements.in`. The recompiled, hash-pinned runtime lock pins the Authlib version that the extra resolves to, and the `lock-check` and `audit` jobs gate it.
- **Log level (Q3 A):** visitor refusals (`not_verified`, `not_listed`) are logged at INFO; `settings_missing`, `allowlist_invalid` and `gate_error` at WARNING. Each is still logged once per reason per browser session, with no email.
- **Carried from the inception NFRs and the approved design:**
  - **NFR1:** fail closed on any secret, settings, allowlist or gate error; no secret, setting value or email in any log or screen.
  - **NFR2:** the gate counts toward the 30-second cold-start target.
  - **NFR3:** test-first with both floors held; the sign-in wiring is covered through the seam.
  - **NFR4:** one refusal line per reason per session.
  - **NFR5:** one h1, text messages, keyboard-reachable buttons.
  - **NFR7:** the new dependency arrives only through the lock and passes `pip-audit`.
  - NFR6 (read-only checks) does not apply to this unit.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
