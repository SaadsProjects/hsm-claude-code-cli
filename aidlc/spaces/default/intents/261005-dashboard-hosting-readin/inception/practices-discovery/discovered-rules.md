# Discovered Rules

## Mandated

- ALWAYS remove the burned signing-secret literal from `mock_hsm/auth.py` and its `TEMPORARY_EXCLUSIONS` entry in `scripts/check_burned_secret.py` in the same commit, with regression tests that the burned-secret check passes, that a missing secret raises a clear error, and that the secret is read at call time. *(M1; source: interview Q11, CQ-2, scope decision D9)*
- ALWAYS change a required CI job's name and the `main_branch_protection` ruleset's required-check list in the same piece of work, because a required check that never reports blocks every pull request. *(M2; source: interview Q11)*

## Forbidden

- NEVER let the post-deploy check sign in as an allowlisted user, or store identity-provider sign-in credentials in CI. *(F1; source: interview Q11)*
- NEVER commit `.streamlit/secrets.toml`, `.env`, `.env.local` or any other `.env.*` file; ignore them with explicit `.gitignore` lines outside the AI-DLC-managed block. *(F2; source: interview Q11, CQ-9)*

## Notes

- The interview dropped a third candidate mandate ("create the hosted apps only after the sign-in gate and secret handling merge"). The standing `project.md` Forbidden rules R-SEC-1 and R-SEC-3 already cover it, and `team-practices.md` § Deployment keeps it as the "Order" practice.
- The standing `project.md` Mandated and Forbidden rules were re-checked at commit `825a0f8`, and none needed rewording. The `browser-tests` job's `-m browser` is a related marker expression, so the rule against an unrelated `-m` still holds. The OIDC-only credential rule still binds nothing today, because CI holds no cloud credential.
