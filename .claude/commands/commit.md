---
description: Review staged changes, then commit if the review and lint gate both pass
argument-hint: <commit message>
---
1. Run `git status` and `git diff` to see what's changed. If nothing is
   staged yet but there are unstaged changes worth committing, stage the
   relevant files with `git add` (ask me first if it's unclear which
   files belong in this commit).
2. Use the code-reviewer subagent to review the staged diff (`git diff
   --staged`).
3. Show me the reviewer's findings.
   - If it found real problems, stop here and let me decide whether to
     fix them first or commit anyway -- do not commit without me saying
     to.
   - If it found nothing, or only things I've said are fine, proceed to
     step 4.
4. Run `git commit -m "$ARGUMENTS"`. Note that this is independently
   gated by a PreToolUse hook that runs `ruff check` and will block the
   commit if the codebase doesn't lint clean, regardless of what the
   review concluded -- if that happens, fix the lint errors and retry the
   commit rather than trying to bypass it.
