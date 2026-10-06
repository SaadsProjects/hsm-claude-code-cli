# Functional Design Questions — U3 sign-in-gate

The contract for this unit (C4, with C6 and C7) already settles a lot:
- the decision outcomes and reasons;
- that only a boolean `True` for `email_verified` counts;
- that the allowlist is a non-empty list of strings, compared trimmed and lower-cased with exact matches only;
- the identity seam (`current_identity`, `sign_in`, `sign_out`);
- that any error refuses with Screen 5;
- the hosted secrets layout;
- the marker names.

Delivery planning settled that using the dashboard locally means creating a local Google sign-in client, so missing sign-in settings show Screen 5 locally as well. These questions cover what is still open.

## Q1 — What does "Sign out" end?

AC4.6.3 says the persona session is cleared at sign-out. Today a persona login also opens a session on the backend (`POST /sessions`), and the existing "Log out" button ends it (`POST /sessions/{id}/logout`).

A. End the persona's backend session if one is open (best effort; a failure is logged but doesn't block sign-out), then clear all of this browser session's dashboard state, then sign out of Google (Recommended)
B. Clear all of this browser session's dashboard state and sign out of Google; leave any backend session to expire on its idle timeout
C. Clear only the persona login and its scoped keys; keep other state such as the last notice
X. Other (please specify)

[Answer]: A

## Q2 — How often is a refusal written to the log?

Streamlit re-runs the page on every interaction, so a refused visitor who stays on Screen 2 or Screen 5 triggers the gate again and again. FR4.10 asks for each refusal to be logged with its reason and never the email.

A. Once per browser session per reason: the first refusal for a reason is logged, and repeats in the same session are not (Recommended)
B. Every time the gate refuses, on every re-run
C. Once per browser session, whatever the reason
X. Other (please specify)

[Answer]: A

## Q3 — When are the sign-in settings "present"?

C7 says a missing `[auth]` or `[auth.google]` section means `settings_missing` (Screen 5). A section can also exist with a key left out or blank, which `st.login` would only reject after the visitor clicks "Sign in".

A. Check the required keys too: `redirect_uri` and `cookie_secret` under `[auth]`, and `client_id`, `client_secret` and `server_metadata_url` under `[auth.google]`, each a non-empty string; anything missing or blank is `settings_missing` (Recommended)
B. Check only that both sections exist, as C7 states, and let `st.login` report missing keys at click time (which then shows Screen 5)
X. Other (please specify)

[Answer]: A

## Q4 — A signed-in identity with no email

Google normally always returns an email, but the seam can report `signed_in` with an empty or missing email. The reasons in C4 have no separate value for this case.

A. Refuse as the visitor's refusal with reason `not_verified` (Screen 2, showing "Signed in as:" with an empty value) — no new reason is added
B. Treat it as a gate error: `refuse_unavailable` with reason `gate_error` (Screen 5, the neutral "Sign-in isn't available right now" wording), because an identity without an email means the provider settings are wrong (Recommended)
C. Add a new reason `no_email` to C4 and show Screen 2
X. Other (please specify)

[Answer]: B

## Consolidated Summary Confirmation

- **Sign out (Q1 A):** "Sign out" ends the persona's backend session if one is open. This is best effort: a failure is logged without the session id and doesn't block sign-out. It then clears all of this browser session's dashboard state, then signs out of Google. The next account on the same tab starts with no persona selected.
- **Refusal log (Q2 A):** each refusal is logged once per browser session per reason (`not_verified`, `not_listed`, `settings_missing`, `allowlist_invalid`, `gate_error`), never with the email. Repeats of the same reason in that session are not logged.
- **Settings present (Q3 A):** the settings count as present only when all five keys are non-empty strings: `[auth]` `redirect_uri` and `cookie_secret`, and `[auth.google]` `client_id`, `client_secret` and `server_metadata_url`. Anything missing or blank is `settings_missing` (Screen 5).
- **No email (Q4 B):** a signed-in identity with an empty or missing email is `refuse_unavailable` / `gate_error` (Screen 5, neutral wording, Sign out shown).
- **From the contract (unchanged):**
  - Startup order on every rerun: SecretsBridge, then the gate, then the embedded backend, then the screens.
  - SecretsBridge copies `HSM_SIGNING_SECRET` from Streamlit secrets only when the environment lacks it. It fails closed on a missing secret, or one equal to `cookie_secret`, with Screen 5 and a log naming the settings but not their values.
  - Only a boolean `True` counts for `email_verified`.
  - The allowlist (`HSM_ALLOWED_EMAILS`) must be a non-empty list of strings, compared trimmed and lower-cased, exact matches only.
  - Any exception inside the gate shows Screen 5.
  - Screen 1, 2 and 5 copy comes from the refined mockups.
  - The Account section sits above the "Demo persona" section, with the "Acting as" caption.
  - `markers.py` holds constants only.
  - Locally, the dashboard needs a local Google sign-in client, so missing settings show Screen 5 there too.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
