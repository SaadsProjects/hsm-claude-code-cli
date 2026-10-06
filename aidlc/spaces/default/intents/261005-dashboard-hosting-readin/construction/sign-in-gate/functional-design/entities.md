# Entities — U3 sign-in-gate

## Sources

- `inception/domain-design/components.md` (SecretsBridge, SignInGate, DashboardShell; VisitorIdentity, Allowlist, GateDecision, PersonaSession)
- `inception/contract-design/contract-summary.md` C4 (SignInGate API), C6 (markers), C7 (hosted secrets schema)
- `inception/user-stories/stories.md` US2.5, US4.1–US4.8, US8.1
- `functional-design-questions.md` Q1–Q4 (answered A, A, A, B; summary confirmed)

## Entity Model

```yaml
entities:
  - name: SignInSettings
    description: >
      The sign-in configuration read from the app's hosted secrets (C7). It is a value read on every rerun and is never
      stored, logged or shown. Owned by SignInGate.
    identifier: none (value object)
    attributes:
      - name: redirect_uri
        type: text
        required: true
        constraints: "non-empty after trimming; under [auth]"
      - name: cookie_secret
        type: secret text
        required: true
        constraints: "non-empty after trimming; under [auth]; must differ from HSM_SIGNING_SECRET (BR1.3)"
      - name: client_id
        type: text
        required: true
        constraints: "non-empty after trimming; under [auth.google]"
      - name: client_secret
        type: secret text
        required: true
        constraints: "non-empty after trimming; under [auth.google]"
      - name: server_metadata_url
        type: text
        required: true
        constraints: "non-empty after trimming; under [auth.google]"
      - name: present
        type: boolean
        required: true
        derived: "true only when all five keys above are non-empty strings (BR2.1)"
    constraints:
      - "Values are never written to a log, a screen or an error message"
    relationships: []

  - name: Allowlist
    description: >
      The set of email addresses allowed in, parsed from the hosted secret HSM_ALLOWED_EMAILS. Owned by SignInGate.
    identifier: source
    attributes:
      - name: source
        type: text
        required: true
        allowed_values: ["HSM_ALLOWED_EMAILS"]
      - name: entries
        type: list of text
        required: true
        constraints: "at least one entry; each entry trimmed and lower-cased; no entry blank after trimming; no wildcards or domain patterns are interpreted"
      - name: valid
        type: boolean
        required: true
        derived: "false when the raw value is missing, not a list, empty, or holds a non-string or blank entry (BR2.2)"
    constraints:
      - "Its contents are never shown to a visitor and never logged"
    relationships: []

  - name: VisitorIdentity
    description: >
      Who the identity provider says the visitor is, as reported by the identity seam for this browser session.
      Owned by SignInGate.
    identifier: email
    attributes:
      - name: signed_in
        type: boolean
        required: true
      - name: email
        type: text
        required: false
        constraints: "may be missing or blank; compared only after trimming and lower-casing; shown only as literal text on Screen 2 and in the Account section"
      - name: email_verified
        type: raw provider value
        required: false
        constraints: "only the boolean value true counts as verified; false, missing, null and any string (including \"true\" and \"false\") do not"
    constraints:
      - "The email is never written to the log"
    relationships:
      - entity: GateDecision
        cardinality: one-to-many
        direction: a decision is made about one identity on each rerun

  - name: GateDecision
    description: >
      The result of one gate evaluation on one rerun. Owned by SignInGate. Not stored; returned to DashboardShell.
    identifier: outcome
    attributes:
      - name: outcome
        type: enum
        required: true
        allowed_values: ["allow", "refuse_visitor", "refuse_unavailable"]
      - name: reason
        type: enum
        required: true
        allowed_values: ["ok", "not_signed_in", "not_verified", "not_listed", "settings_missing", "allowlist_invalid", "gate_error"]
      - name: screen
        type: enum
        required: true
        derived: "allow → Screen 3 or 4 (DashboardShell decides); not_signed_in → Screen 1; not_verified, not_listed → Screen 2; settings_missing, allowlist_invalid, gate_error → Screen 5"
    constraints:
      - "outcome allow pairs only with reason ok"
      - "refuse_visitor pairs only with not_signed_in, not_verified or not_listed"
      - "refuse_unavailable pairs only with settings_missing, allowlist_invalid or gate_error"
    relationships:
      - entity: VisitorIdentity
        cardinality: many-to-one
        direction: each decision refers to the identity reported on that rerun

  - name: RefusalLogMark
    description: >
      The per-browser-session record of which refusal reasons have already been logged, so each reason is logged once
      per session (BR6.2). Held in this browser session's dashboard state; cleared at sign-out with the rest of it.
    identifier: reason
    attributes:
      - name: reason
        type: enum
        required: true
        allowed_values: ["not_verified", "not_listed", "settings_missing", "allowlist_invalid", "gate_error"]
    constraints:
      - "Holds no email and no identity data"
    relationships: []

  - name: PersonaSession
    description: >
      The existing persona login and its per-login state (owned by DashboardShell, defined by the dashboard-writes work).
      Referenced here because sign-out ends and clears it.
    identifier: session_key
    attributes:
      - name: session_key
        type: text
        required: true
      - name: persona
        type: text
        required: false
      - name: backend_session
        type: text
        required: false
        constraints: "the backend session opened by the persona login; never shown or logged"
      - name: account_email
        type: text
        required: false
        constraints: "the trimmed, lower-cased email of the allowed identity this state belongs to; held only in session state, never shown or logged (BR5.2)"
    constraints:
      - "Exists only while one visitor identity is allowed; cleared at sign-out (BR5.1) and when a different account is allowed (BR5.2)"
    relationships:
      - entity: VisitorIdentity
        cardinality: many-to-one
        direction: a persona session belongs to the identity that was allowed when it was opened
```

## Summary

- **SignInSettings** and **Allowlist** come from the hosted secrets. They decide whether the gate can work at all. Their contents are never shown or logged.
- **VisitorIdentity** is what Google reports through the identity seam. Only a boolean `true` verified flag and an allowlisted email let a visitor in.
- **GateDecision** is the per-rerun answer. It picks which screen renders.
- **RefusalLogMark** keeps the refusal log to one line per reason per browser session.
- **PersonaSession** belongs to the existing dashboard. It appears here because sign-out ends it.
