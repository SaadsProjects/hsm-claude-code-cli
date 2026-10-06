# Reverse Engineering Timestamp: hsm-claude-code-cli

- **Date:** 2026-10-05 (developer scan 2026-10-04, architect synthesis 2026-10-05)
- **Commit:** `825a0f8` (branch `main`)
- **Intent:** `261005-dashboard-hosting-readin`
- **Scan type:** full scan of the whole repository (`./`), Standard depth,
  first scan (no prior store)
- **Pipeline:** developer scan
  (`aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/reverse-engineering/developer-scan.md`)
  → architect synthesis (these nine artifacts)

## Coverage Notes

The scan read the application code, hooks, CI workflow, configuration and
test fixtures deeply, weighted toward the code the hosting intent changes.
Areas read only by name or headings are listed under `shallow.paths` below.
AI-DLC tooling (`aidlc/`, `.claude/aidlc-common/`, `.claude/tools/`,
`.claude/skills/aidlc*`, `.claude/agents/aidlc-*`, `.claude/knowledge/`,
`.claude/sensors/`, `.claude/scopes/`, `.claude/rules/`, `.claude/hooks/*.ts`,
`.claude/CLAUDE.md`) was excluded as framework tooling, not project code.

## Scope of Analysis

```yaml
scope_version: 1
kind: full
intent: 261005-dashboard-hosting-readin
fingerprint: f8470864f5ae10c1e0c0407ccb685ca9a098669d
analyzed:
  paths:
    - ./
  components:
    - agents
    - mock_hsm
    - dashboard
    - mcp_server
    - claude-hooks
    - claude-subagents-and-commands
    - scripts
    - tests
    - ci-workflow
shallow:
  paths:
    - dashboard/audit_tab.py
    - dashboard/manage_tab.py
    - dashboard/kind_forms.py
    - dashboard/csv_rows.py
    - dashboard/safe_text.py
    - scripts/check_exceptions.py
    - scripts/check_workflows.py
    - scripts/filter_audit.py
    - scripts/filter_bandit.py
    - scripts/floor_ratchet.py
    - scripts/job_summary.py
    - scripts/test_floor.py
    - README.md
    - docs/ARCHITECTURE.md
    - CLAUDE_CODE_CLI_PLAN.md
    - architecture-diagram.html
    - .github/dependabot.yml
```
