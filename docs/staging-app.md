# Staging app runbook

How the repository owner creates the staging dashboard on Streamlit Community
Cloud and proves it works. Everything here happens in the Google Cloud console,
on Streamlit Community Cloud and on your own machine. Nothing in this runbook
is committed: no app URL, client id, secret or email goes into the repository.

Placeholders used below:

- `<staging-app>`: the app's subdomain, so the app lives at
  `https://<staging-app>.streamlit.app`.
- `<your-email@example.com>`: the Google account that may sign in.

## Before you start

- Pull request #7 (the sign-in gate, the in-process backend, the build caption
  and the post-deploy check) has merged into `main`, with all 10 required
  checks green. No staging app exists before that merge.
- You can sign in to the Google Cloud project and to Streamlit Community Cloud
  with the account that owns `SaadsProjects/hsm-claude-code-cli`.
- Pick the subdomain now, because the OAuth client needs the full URL.

## 1. Create the Google OAuth client

Staging gets its own client; never reuse the one for local runs.

1. In the Google Cloud console, set up the OAuth consent screen if the project
   has none: an external app, your own email as the support and developer
   contact, and the `openid`, `email` and `profile` scopes. While the app is in
   testing, add `<your-email@example.com>` as a test user.

   Add the second account you will use in step 4 (d), the one that is not on
   the allowlist, as a test user too. In testing mode Google blocks every
   account that isn't a test user on its own "Access blocked" page, before it
   reaches the app, so without it step (d) never reaches the gate's refusal.
2. Create an OAuth client id of type **Web application**, named for staging.
3. Add exactly one authorised redirect URI:
   `https://<staging-app>.streamlit.app/oauth2callback`.
4. Keep the client id and client secret for step 2. Don't save them in a file
   inside the repository.

## 2. Prepare the secrets

Generate two fresh values on your machine, one for each secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

`HSM_SIGNING_SECRET` and `cookie_secret` must be different values: run the
command twice and never paste the same output into both. Never reuse the
value from your local `.env.local` either; staging gets its own. If the two
are the same, the gate refuses everyone with
"Sign-in isn't available right now."

Fill in this block with your values in place of the placeholders. You paste it
into the app's Secrets settings in step 3, so keep it somewhere outside the
repository until then. The two top-level keys must come before the `[auth]`
tables: TOML assigns any key to the last table above it, so a top-level key
pasted lower down stops being top-level.

```toml
HSM_SIGNING_SECRET = "<first generated value>"
HSM_ALLOWED_EMAILS = ["<your-email@example.com>"]

[auth]
redirect_uri = "https://<staging-app>.streamlit.app/oauth2callback"
cookie_secret = "<second generated value>"

[auth.google]
client_id = "<staging OAuth client id>"
client_secret = "<staging OAuth client secret>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

`HSM_ALLOWED_EMAILS` takes exact addresses only, no domains or wildcards.
These are the same keys as `.streamlit/secrets.toml.example`.

## 3. Create the app

On Streamlit Community Cloud, create a new app from the GitHub repository:

| Setting | Value |
|---------|-------|
| Repository | `SaadsProjects/hsm-claude-code-cli` |
| Branch | `main` |
| Main file path | `dashboard/app.py` |
| App URL | `<staging-app>` |
| Python version (Advanced settings) | the newest offered that is no newer than 3.14 |

The host installs `requirements.txt`, the runtime lock. CI tests Python 3.10
and 3.14 only. If the Python version you picked is neither, set the
repository variable `HOSTED_PYTHON` to it (GitHub: Settings > Secrets and
variables > Actions > Variables), so CI also tests the version staging runs on.

Open Advanced settings before you deploy and paste the secrets
block from step 2 there, so the first start already has them; without them the
app shows "Sign-in isn't available right now." and nothing else.

If the deploy fails with "the `SaadsProjects` organization has enabled OAuth
App access restrictions", Streamlit hasn't been approved for the organization
yet. The person who connected Streamlit to GitHub opens
github.com/settings/applications, Authorized OAuth Apps, Streamlit. Under
Organization access they click Grant next to the organization if they are an
organization owner; otherwise they click Request, and an owner approves it
under the organization's Settings > Third-party Access. Then deploy again.
Approve Streamlit only; keep the restriction on for every other app.

## 4. Prove it

Do these in order. The check never signs in; steps (c) and (d) are your own
sign-ins.

a. On your machine, with the dev lock and Chromium installed
   (`python -m playwright install chromium`):

   ```bash
   python3 scripts/postdeploy_check.py https://<staging-app>.streamlit.app --timeout 180
   ```

   It must exit `0`. `1` means a check failed, `3` means no answer, still
   waking or never settled, and `4` means the browser could not start.

b. In GitHub, run the `postdeploy` workflow from the Actions tab against the
   same URL. It must pass.

c. Sign in with `<your-email@example.com>`. The dashboard opens, and the
   sidebar's last caption reads `Build <short SHA>` matching the head of `main`
   (or `Build src-<fingerprint>` if the host's checkout has no `.git`).

d. Sign in with a verified Google account that is not on the allowlist (the
   second test user from step 1). You see "This account doesn't have access."
   with Sign out, and no tab.

e. After the next pull request merges into `main`, confirm that staging
   redeploys by itself: once the app has restarted, sign in and check that the
   `Build` caption now shows the new head of `main`, then run (a) again. Until
   a later merge happens this step stays open, so record it as not yet proven.
   The first merge after the app exists closes it.

**Timing (NFR2).** The target is that the app is usable within 30 seconds of
waking. A brand-new app is awake, so first put it to sleep: wait until
Streamlit Community Cloud shows its sleep page for the app (an app with no
visitors sleeps after a while), or reboot it from the app's menu to time a cold
start instead. Then time the check from that state:

```bash
time python3 scripts/postdeploy_check.py https://<staging-app>.streamlit.app --timeout 180
```

Also stopwatch your own sign-in in (c) from the moment the page wakes. Record
both times, and record a miss rather than hiding it. This timed run from a
sleeping app is what closes NFR2; until it is recorded, NFR2 stays open.

## 5. Turn on the automatic check

After every merge to `main`, the `staging-check` workflow waits 3 minutes for
staging to redeploy, then runs the post-deploy check against it. It reads the
address from a repository variable, so set it once: in GitHub, Settings >
Secrets and variables > Actions > Variables, add `STAGING_URL` with the value
`https://<staging-app>.streamlit.app`. Until it is set, every `staging-check`
run fails, saying the variable is missing.

A failed run shows on the merge commit, and GitHub emails whoever merged.
Re-run it once from the Actions tab first, because a slow redeploy can outlast
the 3-minute wait. If it fails again, roll back. The check still can't see the
build, so sign in and read the `Build` caption to be sure the merge is live.

## Rollback

- A bad change on staging: revert it on `main` through a pull request, let the
  app redeploy, then let `staging-check` run on the revert (or run step 4 (a)
  again).
- If the gate ever lets in someone it shouldn't: delete the app first, or
  set `HSM_ALLOWED_EMAILS = []` (an empty allowlist fails closed and refuses
  everyone), and
  investigate afterwards.
- A leaked secret: generate a new value, replace it in the app's Secrets
  settings and reboot the app. For the OAuth client, create a new secret in
  the Google Cloud console, put it in the app's `client_secret` and reboot the
  app, and only then delete the old secret.
