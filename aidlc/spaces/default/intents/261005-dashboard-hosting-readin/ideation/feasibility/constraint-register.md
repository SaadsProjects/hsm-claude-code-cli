# Constraint Register — Dashboard Hosting Readiness

## Sources

- Answers Q1–Q9 in `ideation/feasibility/feasibility-questions.md`
- Rules: `aidlc/spaces/default/memory/{team,project}.md`
- Repository floor files: `.test-floor` (745), `.coverage-floor` (95.00)

## Technical Constraints

| ID | Constraint | Source |
|----|------------|--------|
| C-T1 | The hosted signing secret comes from Streamlit Cloud's secrets store or the environment, never from source code. Without it, the app refuses to start. | Q1/Q8; `project.md` Forbidden |
| C-T2 | The backend is never reachable from outside the dashboard's own process. | `project.md` Forbidden |
| C-T3 | Streamlit Cloud runs a single process, so the backend runs inside the dashboard. | `team.md` Deployment |
| C-T4 | Python 3.10 is the floor, and the code is standard-library first. `mock_hsm/auth.py` stays standard-library only; Streamlit-specific bridging lives in the dashboard. | `team.md` Code Style; `project.md` Code Style |
| C-T5 | All changes pass the existing GitHub Actions CI and its required checks. | Q1/Q8; `project.md` Mandated |
| C-T6 | The post-deploy check is read-only: it never writes data, publishes a schedule or submits a purchase order. | `team.md` Deployment; `project.md` Forbidden |

## Quality Constraints

| ID | Constraint | Source |
|----|------------|--------|
| C-Q1 | Work test-first; tests ship in the same commit as the code they cover. | `team.md` Testing Posture |
| C-Q2 | The test floor (745) and coverage floor (95.00) may only rise. The measured package set is never narrowed. | Repo floor files; `project.md` Forbidden |
| C-Q3 | The burned-secret literal and its temporary scan exclusion are removed in the same change. | Intent statement |

## Organizational Constraints

| ID | Constraint | Source |
|----|------------|--------|
| C-O1 | Every change reaches `main` through a short-lived branch, a pull request and squash merge. Local commits go through `/commit`. | `team.md` Way of Working; `project.md` Mandated |
| C-O2 | You are the sole builder, reviewer and approver. | Intent capture Q5, Q6 |
| C-O3 | Target: done within a week. | Q9 |

## Budget Constraints

| ID | Constraint | Source |
|----|------------|--------|
| C-B1 | Free tier only: Streamlit Community Cloud and free sign-in. | Q4 |

## Regulatory Constraints

None apply (Q2).

## Assumptions & Open Questions

None.
