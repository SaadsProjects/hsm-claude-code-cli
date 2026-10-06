# Scalability Requirements — Dashboard Deployment Pipeline

## Sources

- `requirements.md` constraints (single process, in-memory backend) and NFR6 [requirements]
- NFR questions NQ3 (one allowlisted user) and NQ12 (synthetic data)

## Context

The IDs below are filed under requirements NFR6 (reliability, best effort). Requirements has no separate scalability NFR; these items come from its single-process constraint.

The hosted apps serve exactly one allowlisted person, the owner. Each Streamlit Cloud app is one process with an in-memory backend, and data resets on every restart (a deferred gap). Scaling out is neither possible nor needed. This document records that explicitly, so later stages don't design for load.

## Requirements

| ID | Requirement | Verify |
|---|---|---|
| **NFR6.4** | Each hosted app supports **1** allowlisted user with up to **3** concurrent browser sessions (tabs) without errors. | Manual check at the skeleton checkpoint: open 3 tabs signed in, switch personas in each, and see no exceptions. |
| **NFR6.5** | Each app runs exactly **one** backend instance per process. Streamlit reruns and new sessions reuse it (single-instance guard). | Unit test: calling the start function twice starts one server thread. |
| **NFR6.6** | Data volume is bounded by the seeded dataset (3 sites, fixed rosters and catalogues) plus the writes one user makes before the next reset. No growth planning is required. | None (recorded constraint). |

## Out of scope

- Horizontal scaling, autoscaling, multi-instance state, and capacity planning. They are revisited only when persistence (the deferred follow-up) or more users are added.

## Assumptions & Open Questions

- [assumption] Streamlit Community Cloud's free-tier resource limits (memory and CPU) are enough for the seeded dataset. The current local process footprint is well under 1 GB.
- None.
