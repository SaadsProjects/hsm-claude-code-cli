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

## 6. Staging monitor

Between merges, the `staging-monitor` workflow checks staging every 30 minutes
(at minutes 7 and 37 of each hour). Each run makes one plain request to the
app's Streamlit health path at the `STAGING_URL` address from step 5; it never
signs in, never wakes a sleeping app and never writes data. When staging has
been down on two checks at least 5 minutes apart, the run opens one GitHub
issue labelled `staging-outage` and turns red, so you get the issue
notification and GitHub's failed-run email. The first run that sees staging
answer again comments how long the outage lasted and closes the issue. The run
log of every run shows a `check:` line (what was seen) and a `decision:` line
(what the monitor did); an `error:` line means the monitor itself failed.
A run that stops at once with only a `staging_monitor.py: error:` line and no
`check:` line is misconfigured, usually because the `STAGING_URL` variable is
missing or not an https address; such a run exits with code 2 and checks
nothing.

### When an outage issue opens

The issue says when staging was first seen down, what was seen (the reason,
such as `no-answer`, `timeout`, `error-status`, `redirect` or
`unexpected-page`, and the HTTP status) and links to the run that confirmed
it. Then:

1. Check Streamlit's own status page and the app's page on Streamlit
   Community Cloud. If the host is having trouble, wait; the monitor closes
   the issue once staging answers again.
2. If only this app is down, reboot it from the app's menu on Streamlit
   Community Cloud.
3. If it broke right after a merge, revert that merge through a pull request
   (see Rollback); `staging-check` then runs on the revert.

Closing the issue by hand while staging is still down tells the monitor you
know about it: later runs stay quiet until staging is back, and the next
outage after that opens a new issue.

### What it can and cannot see

- GitHub's schedule is best-effort: runs can start late or be skipped, and
  scheduled runs only run on `main`. With a check every 30 minutes and two
  down checks needed, an alert comes about 30 to 60 minutes after an outage
  starts, later if GitHub runs late. A shorter outage may never alert.
  If GitHub skips runs for more than 90 minutes after a first down check,
  the monitor forgets that check and starts counting again.
- Asleep is not down. Streamlit puts an app with no visitors to sleep, and
  the monitor treats its sleep or waking page as normal and never presses the
  wake button.
- A broken app that still answers `ok` on its health path is not seen: the
  health path says the app's server runs, not that the dashboard works.
  Signing in (step 4 (c)) is still the way to check the dashboard itself.

**Learning what a sleeping app answers.** Nobody has yet seen what the health
path returns while staging sleeps. Until a real sleep has been seen, every
sleep may raise an alert about 30 minutes later if the host answers with a
redirect or a page the monitor doesn't recognise. So in the first days, an
issue whose reason is `redirect` or `unexpected-page` may be a sleep: open
staging in a browser to check. If it was asleep, close the issue, then copy
from that run's log the `check:` line and the `check-detail:` line under it
(status, content type and body length, never the page itself) into a new
issue or pull request, and adjust `SLEEP_WORDING` (or the classifier) in
`scripts/staging_monitor.py` to match.

### Stopping the monitor

If the monitor is noisy or broken, stop it at once in GitHub: Actions >
`staging-monitor` > the "..." menu > Disable workflow. This is a temporary
step: fix or revert the monitor through a pull request, then switch it back
on with Enable workflow. Never leave it disabled without saying so in an
issue.

GitHub also switches scheduled workflows off by itself after 60 days without
activity in the repository, and emails the owner before it does. To switch
the monitor back on, open Actions > `staging-monitor` and click Enable
workflow (or push any commit to `main` before the 60 days run out). If you
see no `staging-monitor` run for more than about 2 hours, check this first.

To make the monitor forget everything it remembered (for example after a bad
state), delete every saved state, not just the newest, because the next run
would fall back to an older one:

```bash
gh cache list --key staging-monitor-state- --limit 1000 --json id --jq '.[].id' | xargs -n1 gh cache delete
```

The next run then starts from nothing; if an outage issue is still open, it
picks that issue up again instead of opening a second one.

### Practice alert

Run this once after the monitor first merges, and again whenever you want to
be sure alerts still reach you. It never touches staging or its issue.

1. In GitHub, Actions > `staging-monitor` > Run workflow, and set
   `practice_address` to an address under the reserved `.invalid` domain,
   which can never answer, such as `https://practice-1.invalid`. Never use
   staging or a host the team does not own. Start the runs yourself, because
   a manual run's failure email goes to whoever started it.
2. That first run records the practice outage and stays green.
3. At least 5 minutes, and less than 90 minutes, later, start a second run
   with the same address. So the drill is two manual runs, at least 5 minutes
   apart. A second run started 90 minutes or more after the first forgets it,
   records a new first sighting and stays green; start one more run within the
   window. The second run opens an issue labelled `staging-outage-practice`,
   titled "Practice: ... is down", and turns red. If a practice run shows as
   cancelled (it can collide with a queued scheduled run), start it again.
4. Close the practice issue by hand. That ends the drill. A later drill can
   use the same address: its first run notices the closed issue and records
   the new drill's first sighting, so it again takes two runs at least 5
   minutes apart.

The drill passes when you receive both the practice issue's GitHub
notification and the failed-run email from the second run. If only the issue
notification arrives, the drill still passes; note here that the issue
notification is the alert to rely on. If neither arrives, the drill fails and
the monitoring work is not done.

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
