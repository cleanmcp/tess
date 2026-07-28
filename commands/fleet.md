---
description: Decompose a goal into parallel tess sessions and spawn them
argument-hint: <goal>
allowed-tools: Bash(tess:*), Read, Grep, Glob, Write
---

Goal: **$ARGUMENTS**

Already running (don't collide):

!`tess status 2>&1 | head -20`

Plan a fleet for that goal:

1. Decompose it into **independent** units of work — pieces that don't need each other's output
   and won't edit the same files. If the work is genuinely sequential, say so and recommend a
   single session instead. Don't manufacture parallelism.
2. For each unit pick a role: `investigate` (read-only, `readonly: true`), `implement`, or `review`.
3. Write a `fleet.yaml`:

```yaml
defaults: { model: claude-sonnet-5, effort: high }
agents:
  - { name: <short>, feature: <kebab-case>, role: implement, prompt: "<specific, self-contained task>" }
```

Each prompt must stand alone — that agent sees none of this conversation.

4. Run `tess team fleet.yaml --dry-run` and show me the plan.
5. **Wait for my go-ahead** before spawning for real. Then `tess team fleet.yaml` and report
   what came up.

Keep it to the smallest number of sessions that actually covers the goal.
