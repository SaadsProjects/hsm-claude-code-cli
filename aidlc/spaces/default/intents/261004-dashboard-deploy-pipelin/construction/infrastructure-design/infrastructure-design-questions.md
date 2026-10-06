# Infrastructure Design — Questions

Almost everything is settled by the approved NFR design. The items below have one sensible answer, so they are decided in the documents rather than asked:
- runner image pinning;
- tolerating pip-audit's non-zero exit before the filter runs (carried reviewer item R-05);
- the `browser` pytest marker (carried R-10);
- how Dependabot groups its PRs;
- the nightly browser-test schedule.

Three choices are yours.

---

### Question 1
What should the two Streamlit Community Cloud apps be called? The names become their public URLs.

A. `hsm-dashboard-staging.streamlit.app` (tracks `main`) and `hsm-dashboard.streamlit.app` (tracks `production`). Their URLs are stored as the repository variables `STAGING_URL` and `PROD_URL`
B. Other names (please specify both)
X. Other (please specify)

[Answer]: A

### Question 2
How should the Google sign-in (OIDC) clients be set up?

A. One Google OAuth client per environment, each with its own redirect URI (`https://<app>/oauth2callback`) and its own client secret and cookie secret. A leaked staging credential can't be used against production
B. One shared Google OAuth client with both redirect URIs. Fewer things to manage, but staging and production share one client secret
X. Other (please specify)

[Answer]: A

### Question 3
Under which Google account should the OAuth clients be registered?

A. A dedicated Google Cloud project, for example `hsm-dashboard-auth`, under your personal Google account, with the OAuth consent screen in "Testing" mode and only your email added as a test user. That is a second allowlist enforced by Google itself
B. The same project, but published ("In production") consent screen, relying only on the in-app allowlist
X. Other (please specify)

[Answer]: B

---

## Consolidated Summary Confirmation

**Mode:** guided

- **App names:** `hsm-dashboard-staging.streamlit.app` tracks `main`, and `hsm-dashboard.streamlit.app` tracks `production`. Their URLs are stored as the repository variables `STAGING_URL` and `PROD_URL` (Q1: A).
- **OIDC clients:** one Google OAuth client per environment, each with its own redirect URI, client secret and cookie secret (Q2: A).
- **Google project:** a dedicated project under your account with a published consent screen. Access is enforced by the in-app allowlist (and `email_verified`) only (Q3: B).

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
