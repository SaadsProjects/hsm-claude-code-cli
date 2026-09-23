---
description: Build next week's labor schedule for an HSM site
argument-hint: <site_id> [--publish]
---
Use the labor-scheduler subagent to build next week's schedule for site
$ARGUMENTS.

Draft only unless the arguments literally include `--publish` — in that
case, ask the subagent to publish once (and only once) `validate_schedule`
reports zero violations.
