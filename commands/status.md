---
description: Show the tess fleet — every running session, BLOCKED first
allowed-tools: Bash(tess status:*), Bash(tess wt:*), Bash(tess report:*), Bash(tess diff:*)
---

Current fleet:

!`tess status 2>&1 || echo "(tess status unavailable — is tess installed and the hcom backend reachable?)"`

Worktrees:

!`tess wt 2>&1 | head -40`

Read that and give me a tight board:

- One line per session: name → state → what it's doing.
- **BLOCKED sessions first** — say exactly what each is waiting on, and what `tess approve` /
  `tess tell` call would unblock it.
- Anything IDLE or DIED, flag it.
- End with the 1–2 things that actually need my decision. Nothing else.

If a session's state is unclear from the table, run `tess report <agent>` for that one only.
