# Agent integration

[← README](../README.md)

A CLI an agent has never heard of is a CLI the agent won't use. `tess wire` fixes that on every agent installed on your machine.

```bash
tess wire              # run by ./install.sh
tess wire --dry-run    # see the plan
tess wire --undo       # take it all back
```

Idempotent. Symlinks, not copies — `tess update` refreshes every wired agent for free.

## Three layers

| Layer | What | Where |
|---|---|---|
| **Skills** | portable `SKILL.md`, loaded only when the task is worktree- or fleet-shaped. Zero tokens until relevant. | `~/.agents/skills/` + `~/.claude`, `~/.cursor`, `~/.codex`, `~/.gemini`, `~/.config/opencode` |
| **Guardrail hook** | denies raw `git worktree add/remove/move`, hands back the `tess new` equivalent. Doesn't rely on the model having read anything. | Claude Code `PreToolUse` · Cursor `beforeShellExecution` |
| **Primer** | `agent-primer.md` between HTML-comment markers, so your own instructions are untouched | `CLAUDE.md` · `AGENTS.md` · `GEMINI.md` |

The guard **fails open** in every ambiguous case — no tess on `PATH`, unparseable input, read-only subcommands — and only ever denies, never grants.

## Claude Code plugin

```
/plugin marketplace add cleanmcp/tess
/plugin install tess
```

Ships the skills, the guardrail, and slash commands: `/tess:status` `/tess:new` `/tess:ship` `/tess:fleet` `/tess:todo`.

`tess wire` detects the plugin and skips its own Claude hooks, so nothing double-fires.

## Why tess is agent-friendly

- Every interactive command **detects whether a human is present**. Run non-interactively and it takes inline params and **fails with guidance instead of hanging**.
- Output is colored in a terminal and **plain when piped**.
- `--json` where it matters: `tess status`, `tess report`, `tess digest`.
- `--help` on any subcommand is safe — it never creates a worktree or spawns anything.
