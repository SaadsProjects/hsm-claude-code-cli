# Business Rules — U3 sign-in-gate

## Sources

- `inception/requirements-analysis/requirements.md` FR2.1, FR4.1–FR4.10, FR8.1, NFR1, NFR4, NFR5
- `inception/contract-design/contract-summary.md` C1, C4, C6, C7
- `inception/refined-mockups/mockups.md` Screens 1, 2, 3 and 5
- `inception/user-stories/stories.md` US2.5, US4.1–US4.8, US8.1
- `memory/team.md` Deployment and Testing Posture; `memory/project.md` corrections (a way out on every error screen; a neutral screen for system refusals)
- `functional-design-questions.md` Q1–Q4

## Rules

```yaml
rules:
  - id: BR1.1
    statement: The hosted signing secret is copied into the environment only when the environment doesn't already hold one.
    category: policy
    applies_to: SecretsBridge
    trigger: the start of every rerun, before the gate
    logic: IF HSM_SIGNING_SECRET is unset or empty in the environment AND the hosted secrets hold HSM_SIGNING_SECRET THEN copy it into the environment ELSE leave the environment unchanged
    violation: not possible by design; an exported value always wins
    source: FR2.1, C7

  - id: BR1.2
    statement: After the copy, the signing secret must pass the shared secret check, or the app fails closed.
    category: validation
    applies_to: SecretsBridge
    trigger: after BR1.1 on every rerun
    logic: IF the shared secret check (require_secret) fails THEN refuse with refuse_unavailable / settings_missing, render Screen 5, and log the name of the missing or invalid setting
    violation: Screen 5; no tab, persona picker or backend call; the log names HSM_SIGNING_SECRET and never its value
    source: FR2.1, FR1.2, NFR1

  - id: BR1.3
    statement: The signing secret must differ from the sign-in cookie secret.
    category: validation
    applies_to: SecretsBridge, SignInSettings
    trigger: after BR1.2, when a cookie secret is configured
    logic: IF cookie_secret is a non-empty string AND it equals HSM_SIGNING_SECRET THEN refuse with refuse_unavailable / settings_missing
    violation: Screen 5; the log names both settings (HSM_SIGNING_SECRET and auth.cookie_secret) and neither value
    source: team.md Deployment (per-environment secrets), C7

  - id: BR1.4
    statement: Streamlit-specific code, including the secrets bridge, lives only in the dashboard package.
    category: constraint
    applies_to: SecretsBridge, TokenAuth
    trigger: always
    logic: IF code reads Streamlit secrets or calls Streamlit THEN it is in dashboard/; mock_hsm/ never imports Streamlit
    violation: a test that scans mock_hsm/ for Streamlit imports fails
    source: FR1.5, FR2.1, team.md Code Style

  - id: BR1.5
    statement: Hosted secrets that can't be read count as absent, never as an error that skips the gate.
    category: policy
    applies_to: SecretsBridge, SignInGate
    trigger: reading the hosted secrets raises (no secrets file, or a file that doesn't parse)
    logic: IF the hosted secrets can't be read THEN treat every hosted key as missing; the environment may still supply HSM_SIGNING_SECRET, and the sign-in settings are then settings_missing
    violation: Screen 5 (through BR1.2 or BR2.1)
    source: FR4.5, NFR1

  - id: BR2.1
    statement: Sign-in settings count as present only when all five required keys are non-empty strings.
    category: validation
    applies_to: SignInSettings
    trigger: every gate evaluation, after the bridge
    logic: IF any of auth.redirect_uri, auth.cookie_secret, auth.google.client_id, auth.google.client_secret, auth.google.server_metadata_url is missing, not a string, or blank after trimming THEN refuse with refuse_unavailable / settings_missing
    violation: Screen 5
    source: FR4.5, C7, functional-design Q3

  - id: BR2.2
    statement: The allowlist must be a non-empty list of non-blank strings; each entry is trimmed and lower-cased.
    category: validation
    applies_to: Allowlist
    trigger: every gate evaluation, after the settings check
    logic: IF HSM_ALLOWED_EMAILS is missing, not a list (a single plain string included), empty, or holds any entry that is not a string or is blank after trimming THEN refuse with refuse_unavailable / allowlist_invalid ELSE use the trimmed, lower-cased entries
    violation: Screen 5
    source: FR4.4, FR4.5, C4 parse_allowlist

  - id: BR2.3
    statement: Allowlist entries are exact addresses; no wildcard or domain matching is interpreted.
    category: constraint
    applies_to: Allowlist, GateDecision
    trigger: every comparison
    logic: IF an entry looks like a domain or pattern (for example example.com or *@example.com) THEN it matches only a visitor email that is exactly that string, which a real email never is
    violation: not possible by design
    source: FR4.4

  - id: BR3.1
    statement: A visitor who isn't signed in sees only the sign-in screen.
    category: authorization
    applies_to: GateDecision
    trigger: the identity seam reports signed_in false (first visit, a cancelled or failed Google sign-in, or an ended session)
    logic: IF settings and allowlist are valid AND signed_in is false THEN refuse_visitor / not_signed_in and render Screen 1
    violation: Screen 1
    source: FR4.1, FR4.7

  - id: BR3.2
    statement: A signed-in identity without an email is a gate error, not the visitor's fault.
    category: authorization
    applies_to: VisitorIdentity, GateDecision
    trigger: signed_in true with the email missing or blank after trimming
    logic: IF signed_in is true AND the email is missing or blank THEN refuse_unavailable / gate_error
    violation: Screen 5 with Sign out
    source: FR4.5, functional-design Q4

  - id: BR3.3
    statement: Only a boolean true verified flag counts as a verified email.
    category: authorization
    applies_to: VisitorIdentity, GateDecision
    trigger: signed_in true with an email present
    logic: IF email_verified is not exactly the boolean true (false, missing, null, or any string such as "true" or "false") THEN refuse_visitor / not_verified
    violation: Screen 2
    source: FR4.3, C4

  - id: BR3.4
    statement: A verified email is allowed only when, trimmed and lower-cased, it exactly equals an allowlist entry.
    category: authorization
    applies_to: VisitorIdentity, Allowlist, GateDecision
    trigger: signed_in true, email present, email_verified true
    logic: IF the trimmed, lower-cased email equals one of the allowlist entries THEN allow / ok ELSE refuse_visitor / not_listed
    violation: Screen 2
    source: FR4.4

  - id: BR3.5
    statement: The allow/refuse decision is a pure function of the identity and the parsed allowlist.
    category: constraint
    applies_to: GateDecision
    trigger: always
    logic: IF decide is called THEN it reads only its two arguments and returns a decision; it makes no Streamlit call, reads no settings, writes no log and has no side effects
    violation: a unit test calling it without Streamlit fails
    source: FR4.6, C4

  - id: BR3.6
    statement: The gate evaluates its checks in a fixed order, and the first failing check decides.
    category: policy
    applies_to: SignInGate
    trigger: every rerun
    logic: IF the signing secret fails (BR1.2, BR1.3) THEN Screen 5 ELSE IF settings are missing (BR2.1) THEN Screen 5 ELSE IF the allowlist is invalid (BR2.2) THEN Screen 5 ELSE decide on the identity (BR3.1–BR3.4)
    violation: not applicable; this rule fixes the order
    source: C4 gate(), team.md Deployment (gate runs before anything else)

  - id: BR3.7
    statement: Any unexpected error inside the gate refuses entry.
    category: policy
    applies_to: SignInGate
    trigger: an exception while reading settings, parsing the allowlist, reading the identity, deciding or rendering a gate screen
    logic: IF anything inside the gate raises THEN refuse_unavailable / gate_error, render Screen 5, and log the reason with the error type only
    violation: Screen 5; the persona picker and tabs never render
    source: FR4.5

  - id: BR4.1
    statement: Nothing but the gate's own screen renders unless the decision is allow.
    category: authorization
    applies_to: DashboardShell
    trigger: every rerun
    logic: IF the decision is not allow THEN render only Screen 1, 2 or 5 and stop the rerun; no sidebar persona section, no site picker, no tabs, no banner and no backend start or backend call
    violation: not possible by design; an AppTest render-tree check fails
    source: FR4.1, team.md Testing Posture

  - id: BR4.2
    statement: The refused-visitor screen uses one wording for every visitor reason and shows the email only as literal text.
    category: policy
    applies_to: GateDecision (refuse_visitor except not_signed_in)
    trigger: not_verified or not_listed
    logic: IF the visitor is refused THEN show "This account doesn't have access.", "Signed in as: " plus the email rendered as literal text (no markup interpreted), and a Sign out button; never show the reason or any allowlist content
    violation: not applicable; this rule fixes the copy
    source: FR4.8

  - id: BR4.3
    statement: The unavailable screen is neutral and keeps a way out.
    category: policy
    applies_to: GateDecision (refuse_unavailable)
    trigger: settings_missing, allowlist_invalid or gate_error
    logic: IF the refusal is refuse_unavailable THEN show "Sign-in isn't available right now." and "Reload the page or try again later." with no technical detail; then read the identity through the seam in its own guarded call (on every path, including the secret, settings and allowlist failures) and show Sign out only when that read succeeds and reports a signed-in identity; a failed read shows no Sign out, and the reload line is the way out
    violation: not applicable; this rule fixes the copy
    source: AC4.4.3, project.md corrections, functional-design review R-02

  - id: BR4.4
    statement: Each gate screen has exactly one h1, plain-text messages and a keyboard-reachable action.
    category: constraint
    applies_to: Screens 1, 2 and 5
    trigger: rendering a gate screen
    logic: IF a rerun starts THEN the shared page header (page setup, which Streamlit requires as its first call, then the app title "HSM labor & inventory" as the only h1) renders first, before the bridge and the gate, on every path; a gate screen adds only its message in text (never colour alone) and its action (Sign in with Google, or Sign out) as a standard button reachable with Tab and activated with Enter
    violation: an AppTest or browser test fails
    source: NFR5, functional-design review R-06

  - id: BR4.5
    statement: Sign in starts Google sign-in through the identity seam.
    category: policy
    applies_to: SignInGate identity seam
    trigger: the visitor chooses "Sign in with Google" on Screen 1
    logic: IF Sign in is chosen THEN the seam calls Streamlit's login with the provider name "google"; a committed secrets example carries the [auth] and [auth.google] keys with placeholder values only
    violation: not applicable
    source: FR4.2, C7

  - id: BR4.6
    statement: An allowed visitor's sidebar starts with the Account section, above the Demo persona section.
    category: policy
    applies_to: DashboardShell
    trigger: decision allow (Screen 3, and Screen 4 when the backend didn't start)
    logic: IF allowed THEN the sidebar's first element is the "Account" heading with the email as literal text and a Sign out button; on Screen 3 a divider and the "Demo persona" section follow, and the persona caption reads "Acting as {name} ({persona})"
    violation: not applicable
    source: FR4.9

  - id: BR4.7
    statement: Screen markers are plain constants shared with the tests and the post-deploy check.
    category: constraint
    applies_to: Marker
    trigger: always
    logic: IF a gate screen, the Account section or a Sign in / Sign out button renders THEN it carries its marker from the markers module, which holds string constants only and imports nothing but typing helpers
    violation: a test fails
    source: FR7.5, C6

  - id: BR5.1
    statement: Sign out ends the persona's backend session, clears the browser session's dashboard state, then signs out of Google, in two separately testable parts.
    category: policy
    applies_to: PersonaSession, VisitorIdentity
    trigger: Sign out chosen on Screen 2, 3, 4 or 5
    logic: >
      IF Sign out is chosen THEN first run end_visitor_session, a plain function outside the identity seam that touches only the
      browser session's dashboard state: (1) if a persona login holds a backend session, ask the backend to end it, best effort,
      swallowing only the backend-not-running, backend-unavailable and backend-API errors and logging a failure without the session
      id; (2) clear every dashboard key of this browser session: the persona login, the notice, every login-scoped item (held
      writes, pending delete and retry, audit page, request ids, templates, record cache), the record-form widget keys, the
      RefusalLogMark and the identity binding (BR5.2). It does not reuse the existing persona "Log out" action, which sets a
      "You logged out." notice. THEN call the seam's sign_out, which wraps only the provider sign-out. If the provider sign-out
      raises (for example, broken sign-in settings), the state stays cleared and the next rerun shows Screen 5 or Screen 1.
    violation: not applicable; the next rerun shows Screen 1 (or Screen 5 if the sign-in settings are broken)
    source: AC4.6.2, AC4.6.3, functional-design Q1, functional-design review R-01 and R-03

  - id: BR5.2
    statement: A persona login belongs to the account that opened it and is cleared when a different account is allowed in.
    category: policy
    applies_to: PersonaSession, VisitorIdentity
    trigger: an allowed rerun (decision allow)
    logic: IF this browser session holds dashboard state bound to an account email AND the allowed identity's trimmed, lower-cased email differs from it THEN run end_visitor_session (BR5.1) before rendering, then bind the state to the new email; the bound email is held only in session state and is never logged or shown
    violation: not applicable; the new account starts with no persona selected
    source: AC4.6.3, functional-design review R-05

  - id: BR6.1
    statement: Each logged refusal carries its reason and never the email.
    category: policy
    applies_to: GateDecision
    trigger: a refusal with a reason other than not_signed_in
    logic: IF the gate refuses for not_verified, not_listed, settings_missing, allowlist_invalid or gate_error THEN write one log line naming the reason (and, for gate_error, the error type), with no email, no identity data and no secret value
    violation: a captured-log test fails
    source: FR4.10, NFR4

  - id: BR6.2
    statement: A refusal reason is logged once per browser session.
    category: policy
    applies_to: RefusalLogMark
    trigger: before writing a refusal log line
    logic: IF this browser session's RefusalLogMark already holds the reason THEN skip the log line ELSE write it and add the reason
    violation: not applicable
    source: functional-design Q2

  - id: BR6.3
    statement: No secret or sign-in setting value is ever logged or shown.
    category: constraint
    applies_to: SecretsBridge, SignInGate
    trigger: always
    logic: IF a log line or screen mentions a setting THEN it names the setting and never its value
    violation: a captured-log test fails
    source: NFR1, C2

  - id: BR7.1
    statement: The identity seam is the only code that touches Streamlit's sign-in API, so tests substitute a fake identity there.
    category: constraint
    applies_to: SignInGate identity seam
    trigger: always
    logic: IF code needs the current identity, sign-in or the provider sign-out THEN it goes through the seam, and the seam holds nothing else (no state clearing, no backend call); the existing dashboard AppTest suite runs through the gate with a shared fake allowed identity, and sign-out tests patch only the seam so end_visitor_session still runs
    violation: a test fails
    source: FR4.6, AC4.8.1, functional-design review R-01
```

## Rules Summary

| ID | Rule | Category | Applies to |
|----|------|----------|------------|
| BR1.1 | Copy the hosted signing secret only when the environment lacks one | policy | SecretsBridge |
| BR1.2 | A signing secret that fails the shared check means Screen 5 | validation | SecretsBridge |
| BR1.3 | The signing secret must differ from the cookie secret | validation | SecretsBridge |
| BR1.4 | Streamlit code lives only in `dashboard/` | constraint | SecretsBridge, TokenAuth |
| BR1.5 | Unreadable hosted secrets count as absent | policy | SecretsBridge, SignInGate |
| BR2.1 | All five sign-in keys must be non-empty strings | validation | SignInSettings |
| BR2.2 | The allowlist is a non-empty list of non-blank strings, trimmed and lower-cased | validation | Allowlist |
| BR2.3 | No wildcard or domain matching | constraint | Allowlist |
| BR3.1 | Not signed in means Screen 1 | authorization | GateDecision |
| BR3.2 | Signed in without an email is a gate error (Screen 5) | authorization | GateDecision |
| BR3.3 | Only a boolean `true` verified flag counts | authorization | GateDecision |
| BR3.4 | Exact trimmed, lower-cased allowlist match allows | authorization | GateDecision |
| BR3.5 | The decision is a pure function | constraint | GateDecision |
| BR3.6 | Checks run in a fixed order: secret, settings, allowlist, identity | policy | SignInGate |
| BR3.7 | Any error inside the gate refuses (Screen 5) | policy | SignInGate |
| BR4.1 | Only the gate screen renders unless allowed | authorization | DashboardShell |
| BR4.2 | One refusal wording; email as literal text | policy | Screen 2 |
| BR4.3 | Neutral unavailable screen; Sign out only when a guarded identity read shows a signed-in visitor | policy | Screen 5 |
| BR4.4 | Shared header first; one h1, text messages, keyboard-reachable action | constraint | Screens 1, 2, 5 |
| BR4.5 | Sign in calls Google sign-in through the seam | policy | Identity seam |
| BR4.6 | Account section first in the sidebar | policy | DashboardShell |
| BR4.7 | Markers are plain shared constants | constraint | Marker |
| BR5.1 | Sign out: a plain function ends the backend session and clears state, then the seam signs out of Google | policy | PersonaSession |
| BR5.2 | A different allowed account clears the previous account's persona | policy | PersonaSession |
| BR6.1 | Refusals logged with reason, never the email | policy | GateDecision |
| BR6.2 | Each reason logged once per browser session | policy | RefusalLogMark |
| BR6.3 | No secret or setting value logged or shown | constraint | SecretsBridge, SignInGate |
| BR7.1 | The seam is the only sign-in API caller and holds nothing else; tests use a fake identity | constraint | Identity seam |
