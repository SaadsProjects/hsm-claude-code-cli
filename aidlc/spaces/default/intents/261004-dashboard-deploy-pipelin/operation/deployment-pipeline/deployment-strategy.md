# Deployment Strategy — Dashboard Deployment Pipeline (staging only)

## Sources

- `construction/infrastructure-design/infrastructure-specification.md` — compute model, apps, environments [infrastructure-specification]
- `construction/infrastructure-design/cicd-pipeline.md` — delivery model [cicd-pipeline]
- `construction/ci-pipeline/quality-gates.md` — merge gates [quality-gates]
- `construction/ci-pipeline/ci-config.md` — required checks [ci-config]
- `deployment-pipeline-questions.md` Q1–Q4 (all A)
- Team rules, Deployment (smoke checks, rollback)

## Strategy

**Recreate, by the host.** Streamlit Community Cloud runs one process per app and replaces it when the tracked branch moves. There is no traffic split, so blue/green, canary and rolling updates aren't available, and none is needed for a single-user demo whose data resets on restart [infrastructure-specification].

| Facet | Choice |
|---|---|
| Environments | Local, CI (ephemeral runners), staging. Production was removed on 2026-10-06 |
| Staging | `https://hsm-stg.streamlit.app`, tracks `main`, redeploys on every merge |
| Promotion gates | None beyond merge: the 10 required checks on the pull request are the only gate [quality-gates] |
| Production approval | Not applicable |
| Post-deploy verification | `staging-check.yml` after every merge (Q1 A), waiting 3 minutes first (Q2 A) |
| Failure signal | GitHub's failed-run email (Q3 A) |
| Feature flags | None. The demo has no partial-rollout need; unfinished work stays off `main` |
| Database migrations | None. Data is in memory and resets on every redeploy |

## Environment promotion matrix

| From | To | Trigger | Gate | Verification |
|---|---|---|---|---|
| Pull request branch | `main` | Squash merge by the owner | 10 required checks green, branch up to date [ci-config] | — |
| `main` | Staging app | Automatic (Cloud redeploy) | None | `staging-check.yml` |

## Definition of a finished deploy

A merge's deploy is finished when `staging-check.yml` passes on that commit (team rules: a deploy is not done until the check passes). To be sure the merged commit is the one running, the owner signs in and reads the sidebar build caption, since the check can't see it.

## Assumptions & Open Questions

- [assumption] The app stays on the Streamlit Community Cloud free tier, single container, with no scaling.
- None.
