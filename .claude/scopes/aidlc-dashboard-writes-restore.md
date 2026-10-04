---
name: dashboard-writes-restore
depth: Minimal
keywords: []
guard_policy: relaxed
---

# dashboard-writes-restore scope

Restore the dashboard data writes from commit a189674 (sessions, the 11-kind Manage data tab, the audit trail and client retry, reverted by 2eb1a8d) and reconcile them with what changed since: merge its CLAUDE.md dashboard and audit paragraphs with the hooks-in-`settings.local.json` text, keep only its `mock_hsm/audit/` line in .gitignore so the AI-DLC block isn't duplicated, and make sure the `streamlit>=1.64` dependency is installed. Then verify with the restored tests plus the existing suite. Only setup, code-generation and build-and-test run, because the design and requirements work is already in the commit.

Guard Policy `relaxed`: a change to an input after it was approved is recorded once and the human is told in one line, instead of reopening that approval. The plan-approval and review-freeze checks stand aside. Every gate still asks.
