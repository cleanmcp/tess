---
description: Show the persistent tess todo list and pick up the next item
argument-hint: [add <text> | done <id> | filter]
allowed-tools: Bash(tess todo:*), Read, Grep, Glob
---

!`tess todo 2>&1`

$ARGUMENTS

If I passed `add`/`done`/`rm` above, run that `tess todo` subcommand and confirm in one line.

Otherwise: group the open items by project, flag anything that looks stale or already done based
on the repo, and tell me the single next one worth picking up and why. Don't read the whole list
back to me.
