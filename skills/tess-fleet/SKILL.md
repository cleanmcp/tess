---
name: tess-fleet
description: Use tess to spawn, monitor, steer, and ship multiple parallel AI coding sessions. Trigger when the user wants work done by background/parallel agents, mentions "spawn an agent", "run these in parallel", "fan out", "fleet", "background agent", "delegate this", "kick off", "have an agent do X", "check on the agents", "what are they working on", "ship that", "open a PR for", or asks to monitor/unblock/steer work already running. Each session gets its own worktree, model, effort, role, and budget.
---

# The fleet — many sessions at once

A **session** = one git worktree + one agent + the context it holds. tess spawns it, verifies the
launch actually took (model, effort, and prompt don't always survive the PTY), and gives you one
place to watch, steer, and ship it.

**Check it exists first:** `command -v tess`. The fleet layer also needs the `hcom` backend —
tess runs it via `uvx hcom` if [uv](https://docs.astral.sh/uv) is installed. If either is missing,
tess says so; report that to the user instead of improvising your own agent-launching.

## Spawning

```bash
tess claude <feature> "<task>"  [--model M] [--effort E] [--readonly] [--budget N] [--auto]
tess kimi   <feature> "<task>"  …   # same shape, Kimi's own models + thinking levels
```

The worktree is created if missing. Roles are **enforced, not suggested**: `--readonly` runs the
agent in plan mode, deploy commands are denied unless `--can-deploy`, and `--budget N` is a hard
USD cap checked at spawn (`tess spend` is the ledger).

Fan out a whole fleet from a spec — **always `--dry-run` first** and show the user the plan:

```yaml
# fleet.yaml
defaults: { model: claude-sonnet-5, effort: high }
agents:
  - { name: cache, feature: redis-cache, role: implement,   prompt: "add a redis cache to the hot read path" }
  - { name: audit, feature: sec-audit,   role: investigate, prompt: "audit auth middleware for authz gaps", readonly: true }
```

```bash
tess team fleet.yaml --dry-run     # the exact spawn plan
tess team fleet.yaml               # spawn them
tess orchestrate "<goal>"          # hire an AI lead: decomposes, spawns, unblocks, reports
tess orchestrate off               # take command back
```

Roles (`investigate` / `implement` / `review`) come from `templates/`; users can override them in
`~/.config/tess/templates/`.

## Monitoring

```bash
tess status              # the fleet table — BLOCKED sessions first  (--json for parsing)
tess digest              # everyone's last report, merged
tess report <agent>      # one session's full last message
tess diff <agent|feat>   # what a session ACTUALLY changed (per-worktree diffstat)
tess wait <feat|all>     # block until done — exit code 2 means someone needs approval
tess inbox               # your fleet mail
```

When the user asks "how's it going", run `tess status` — don't guess from memory. BLOCKED sessions
are the ones that need a human; surface those first and say what they're asking for.

## Steering

```bash
tess tell <agent|feat|all> -- <msg>   # message a running session (safe @-escaping)
tess inject <agent> -- <text>         # force a prompt into its terminal; waits and confirms it landed
tess approve <agent>                  # answer a blocked approval dialog
tess watch on [--phone]               # escalation daemon: BLOCKED / IDLE / DIED pings the lead
tess kill <agent|feat>                # stop one
```

`tell` is a message the session reads on its next turn; `inject` forces a turn *now*. Use `tell`
by default.

## Shipping

```bash
tess ship <feature> [--merge] [--dry-run]   # diff → tests → push → PR → optional squash-merge
tess done <feature> --yes                   # teardown: kill its agents + panes + worktrees
```

Never tear down a feature you didn't create without asking. `tess ship --dry-run` before a real
ship if the user hasn't seen the diff.

## Reporting back as an agent

The human is **@bigboss**. When you finish work inside a tess-spawned session, report with:

```bash
uvx hcom send --intent inform -- "@bigboss <one-line result + what needs their call>"
```

That lands in their `tess inbox`. Escalations for blocked/idle/dead sessions are automatic via
`tess watch`. Everything else goes through a first-class `tess` command, not raw backend calls.

## Resuming

```bash
tess resume     # pick ANY past Claude/Kimi session from any folder, chosen by AI summary
```

## Don't

- Don't launch background agents by hand (`claude -p … &`) when tess is installed — you lose
  isolation, the status table, budgets, and teardown.
- Don't spawn a fleet the user didn't ask for. Propose the `fleet.yaml`, show `--dry-run`, wait.
- Don't parse the colored human output — pipe it or use `--json` where offered
  (`tess status --json`, `tess report --json`, `tess digest --json`).
