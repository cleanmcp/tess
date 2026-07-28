---
description: Review a tess feature's diff, then ship it — tests, push, PR
argument-hint: <feature> [--merge]
allowed-tools: Bash(tess:*), Bash(git diff:*), Bash(git log:*), Read, Grep
---

Ship: **$ARGUMENTS**

What this feature actually changed:

!`tess diff $ARGUMENTS 2>&1 | head -60`

Dry run of the ship:

!`tess ship $ARGUMENTS --dry-run 2>&1 | head -40`

Now:

1. Summarize the diff in 3–5 bullets — what changed and why, not a file list.
2. Call out anything that shouldn't ship: debug prints, commented-out code, secrets, a
   half-finished path, a test that was weakened rather than fixed.
3. If the dry run shows failing tests, **stop** and show me exactly what's red. Don't ship it.
4. If it's clean, run the real `tess ship <feature>` (add `--merge` only if I asked for it) and
   report the PR URL.
5. Ask before `tess done <feature>` — teardown is separate from shipping.
