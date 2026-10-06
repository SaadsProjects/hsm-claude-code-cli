# Frontend Components — U3 sign-in-gate

## Sources

- `inception/refined-mockups/mockups.md` Screens 1–5 and `interaction-spec.md`
- `inception/contract-design/contract-summary.md` C4 (gate API), C5 (frame slots), C6 (markers)
- `functional-spec.md`, `rules.md` in this directory

## Component Hierarchy

```
DashboardShell (every rerun)
├── PageHeader                            (page setup first, then the single h1; every path; W1 step 0)
├── SecretsBridge                         (no UI; W1 steps 1–2)
├── SignInGate.gate()                     (W1 steps 3–8)
│   ├── SignInScreen        — Screen 1    [SIGN_IN_SCREEN]
│   │   └── SignInButton    "Sign in with Google"      [SIGN_IN_BUTTON]
│   ├── RefusalScreen       — Screen 2    [REFUSAL_SCREEN]
│   │   └── SignOutButton                              [SIGN_OUT_BUTTON]
│   └── UnavailableScreen   — Screen 5    [UNAVAILABLE_SCREEN]
│       └── SignOutButton   (only when signed in)      [SIGN_OUT_BUTTON]
└── (allow) SignedInFrame
    ├── Sidebar
    │   ├── AccountSection  "Account" + email + Sign out   [ACCOUNT_SECTION], [SIGN_OUT_BUTTON]
    │   ├── Divider                          (Screen 3 only)
    │   ├── DemoPersonaSection "Demo persona" (existing persona login, site picker, "Acting as" caption; Screen 3 only)
    │   ├── backend caption                  (U2)
    │   └── build_caption_slot               (U4)
    └── Main
        ├── h1 "HSM labor & inventory"
        ├── banner_slot                      (U4; Screen 3 only)
        └── existing tabs [APP_TABS], or Screen 4 body [BACKEND_FAILED_SCREEN] (U2)
```

## Components

### PageHeader (every screen)

- Runs first on every rerun, on every path:
  1. the page setup, which Streamlit requires as its first call;
  2. the h1 "HSM labor & inventory".
- No gate screen, frame or tab renders its own h1 or repeats the page setup. That keeps exactly one h1 per screen (BR4.4).

### SignInScreen (Screen 1)

- **Props:** none.
- **State:** none.
- **Renders:**
  - the h1 title;
  - the line "Access to this demo is by invitation.";
  - one button, "Sign in with Google".
- **Interaction:** the button calls the seam's `sign_in`. Focus reaches it with Tab, and Enter activates it.
- **Marker:** the container carries `SIGN_IN_SCREEN`, and the button carries `SIGN_IN_BUTTON`.

### RefusalScreen (Screen 2)

- **Props:** the identity's email.
- **State:** none.
- **Renders:**
  - the h1 title;
  - "This account doesn't have access.";
  - "Signed in as: " followed by the email, rendered as literal text with no Markdown or HTML interpreted;
  - "Sign out".
- **Rule:** the wording is the same for `not_verified` and `not_listed`, and no allowlist content is shown (BR4.2).

### UnavailableScreen (Screen 5)

- **Props:** none. The screen reads the identity itself, through the seam, in its own guarded call, on every path that reaches it.
- **State:** none.
- **Renders:**
  - the h1 title;
  - "Sign-in isn't available right now.";
  - "Reload the page or try again later.";
  - "Sign out" only when the guarded read succeeds and reports a signed-in identity. A failed read shows no button, and the reload line is the way out (BR4.3).
- **Rule:** no technical detail, error type, setting name or address is shown.

### AccountSection (Screens 3 and 4)

- **Props:** the identity's email.
- **Renders:**
  - an h3 "Account";
  - the email as literal text;
  - "Sign out".
- **Placement:** always the sidebar's first element (BR4.6).

### DemoPersonaSection (Screen 3)

- The existing persona login and site picker, unchanged, under an h3 "Demo persona" after a divider.
- The existing caption "Logged in as {name} ({persona})" becomes "Acting as {name} ({persona})".

### SignOutButton

- **Behaviour:** runs W4 in two calls:
  1. `end_visitor_session`, a plain function outside the seam, which ends the backend session (best effort) and clears every dashboard key of this browser session;
  2. the seam's `sign_out`, which only signs out of Google.

  Tests replace only the seam, so the state clearing still runs under test (BR5.1, BR7.1).
- **Placement:** appears on Screens 2, 3, 4 and 5 (Screen 5 only when signed in).
- **Marker:** carries `SIGN_OUT_BUTTON`. The marker name stays the same on every screen, because the same element type is meant.

## State Design

| State | Holder | Lifetime | Cleared by |
|-------|--------|----------|------------|
| Identity | the seam, read from Streamlit's user object on every rerun | the Google session | Sign out |
| RefusalLogMark (logged reasons) | this browser session's dashboard state | browser session | Sign out |
| Account binding (the allowed email the state belongs to; never logged or shown) | this browser session's dashboard state | until a different account is allowed | Sign out, or a different allowed account (BR5.2) |
| Persona login and its scoped state | this browser session's dashboard state (existing) | persona login | Sign out, Log out (existing) |
| Gate decision | none: recomputed every rerun | one rerun | — |

## Interaction Flows

- **First visit:** Screen 1 → Sign in with Google → Google → back to the app:
  - Screen 3 if verified and listed;
  - Screen 2 if verified but not listed, or not verified;
  - Screen 5 if Google returns no email.
- **Refused visitor:** Screen 2 → Sign out → Screen 1.
- **Allowed visitor:** Screen 3 → Sign out → Screen 1. The next account starts with no persona selected.
- **Broken settings:** any screen → Screen 5. Sign out only if signed in; otherwise reload.

## Form Validation

The gate has no form. The only inputs are the two buttons.

## Integration Points

- **Identity seam (C4):** `current_identity()`, `sign_in()` and `sign_out()` are the only calls into Streamlit's sign-in API. The seam holds nothing else (BR7.1).
- **`end_visitor_session` (new, in the gate module, outside the seam):** ends the backend session and clears the dashboard state. Used by Sign out and by BR5.2.
- **Shared secret check (C1):** `require_secret()` runs after the bridge.
- **Embedded backend (C3):** started only after the gate allows.
- **Backend session end:** the existing session-end route, used once at sign-out, best effort.
- **Frame slots (C5):** `banner_slot` and `build_caption_slot` are left for U4.
