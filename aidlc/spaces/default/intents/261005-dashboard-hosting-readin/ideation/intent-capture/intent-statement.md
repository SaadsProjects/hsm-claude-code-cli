# Intent Statement — Dashboard Hosting Readiness

## Problem Statement

The HSM dashboard can't be hosted safely yet. It has no sign-in, its token-signing secret is public, and its backend runs as a separate process. The parked deploy work can't continue until these application changes land. [Q1]

The project's own rules forbid hosting it in this state:
- The dashboard must never be reachable beyond loopback or a private network without a sign-in layer in front of it. [memory:M1]
- A deploy beyond localhost must never use the hard-coded signing secret. Hosted deploys read the secret from the environment and refuse to start without it. [memory:M2]

The changes this work delivers were already specified in the earlier deploy-pipeline design (intent `261004-dashboard-deploy-pipelin`). In plain terms, they are: [desc]
- a sign-in gate that admits only verified emails on an allowlist; [desc]
- the signing secret supplied from configuration, with the burned value deleted from the code and its temporary scan exclusion removed in the same change; [desc]
- the supporting tools (hooks, the tool server, start scripts) refusing to run without a configured secret; [desc]
- the backend running inside the dashboard's own process, reachable only locally, with only one copy allowed to run; [desc]
- a visible build identifier; [desc]
- a banner saying the demo data resets; [desc]
- a read-only post-deploy check, backed by browser tests. [desc]

The work is to be built test-first. [desc]

## Target Customer

The beneficiary is you, the repository owner and developer. Landing these changes unblocks the deploy work. [Q2]

## Success Metrics

| Metric | Pass condition | Source |
|--------|----------------|--------|
| Changes go through CI | Every change reaches `main` through a pull request with all required CI checks passing | [Q3] |
| Burned secret gone | The burned-secret check passes with its temporary exclusion removed | [Q3] |
| Quality floors held | The test count and coverage stay at or above their current floors | [Q3] |
| Sign-in enforced | A browser test shows that a visitor who isn't on the allowlist is turned away | [Q3] |

## Initiative Trigger

The deploy-pipeline work is parked until these application changes exist. [Q4]

## Initial Scope Signal

- Workflow-selected scope: `feature`. [scope]
- User-confirmed boundary: you confirmed the `feature` scope and its full process. [Q8]

## Assumptions & Open Questions

None.
