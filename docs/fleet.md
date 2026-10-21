# Sessions & the fleet

[← README](../README.md)

A **session** = one git worktree + one agent + the context it's holding.

## Spawn one

```bash
tess claude <feature> "<task>"  [--model M] [--effort E] [--readonly] [--budget N] [--auto]
tess kimi   <feature> "<task>"  …          same shape, Kimi's own models + thinking level
tess resume                     resume ANY past session, any folder, picked by AI summary
```

The worktree is created if missing. tess then **verifies** the model, effort and prompt actually applied — launch flags don't always survive the PTY.

Roles are enforced, not suggested:

| Flag | Effect |
|---|---|
| `--readonly` | agent runs in plan mode |
| `--budget N` | hard USD cap (`claude --max-budget-usd`) |
| `--can-deploy` | lifts the deny-list; without it, deploy commands are blocked |
| `--auto` | starts in auto-permission mode, footer-verified |

Dependencies are checked **before** anything touches disk, and a failed launch rolls its worktree back — you never inherit an orphan.

## Watch them

```bash
tess status              the fleet table — BLOCKED first   (--json to parse)
tess digest              everyone's last report, merged
tess report <agent>      one session's full last message
tess diff <agent|feat>   what it actually changed (per-worktree diffstat)
tess wait <feat|all>     block until done — exit 2 = someone needs approval
tess inbox               your fleet mail
```

## Steer them

```bash
tess tell <agent|feat|all> -- <msg>   message it (reads on its next turn) — default choice
tess inject <agent> -- <text>         force a turn NOW; waits and confirms it landed
tess approve <agent>                  answer a blocked approval dialog
tess watch on [--phone]               daemon: BLOCKED / IDLE / DIED pings you
tess kill <agent|feat>                stop one
```

## Fan out

```yaml
# fleet.yaml
defaults: { model: claude-sonnet-5, effort: high }
agents:
  - { name: cache, feature: redis-cache, role: implement,   prompt: "add a redis cache to the hot read path" }
  - { name: audit, feature: sec-audit,   role: investigate, prompt: "audit auth for authz gaps", readonly: true }
```

```bash
tess team fleet.yaml --dry-run    # always look first
tess team fleet.yaml
```

Roles (`investigate` / `implement` / `review`) come from `templates/`; override them in `~/.config/tess/templates/`.

## Hand over the whole fleet

```bash
tess orchestrate "<goal>"    an AI lead: decomposes, spawns, unblocks, verifies, reports
tess orchestrate off         you take command back; agents keep running
tess boss                    interactive orchestrator across all your projects
tess loop claude "<goal>"    autonomous manager→worker loop until DONE
```

## Ship and tear down

```bash
tess ship <feature> [--merge] [--dry-run]   diff → tests (TESS_TEST_CMD) → push → PR (gh)
tess done <feature> --yes                   kill agents + panes + worktrees
tess spend                                  budget ledger
```

Uncommitted changes block a repo from shipping. `tess done` only touches agents working inside that feature's directory.

## Reach another machine's localhost

```bash
tess tunnel mini 3000            its :3000 becomes http://localhost:3000 here
tess tunnel mini 3000 5173       several at once
tess tunnel mini 3900:3000       different local port, when 3000 is taken here
tess tunnel mini --login         the ports a CLI sign-in redirects to
tess tunnel mini --bg 3000       detach · --list shows them · --stop closes them
```

Peers come from the same setting handoff uses:

```bash
TESS_PEERS="mini=mac-mini  box=dev@10.0.0.5"     # ~/.config/tess/config
```

**Seeing what an agent built.** A dev server binds `127.0.0.1`, so nothing off that machine
can reach it — and changing the bind address would put it on the network. Forwarding the port
keeps it private and makes it arrive as plain `localhost`, which is also the origin that
cookies, CORS rules and OAuth redirect allow-lists already expect.

**Signing in on a machine with no screen.** A CLI sign-in opens a browser and waits for a
redirect to `127.0.0.1:<port>` on the machine that started it. Over ssh the browser is here and
the listener is there, so the redirect lands on the wrong computer and the sign-in hangs.
Forward the port first and this machine's localhost *is* that listener. `--login` covers the
ports the common agent CLIs use; one that prints its own port needs `tess tunnel <peer> <that>`.

The forward is plain `ssh -L` — nothing listens on an external interface.

## Reporting back, as an agent

The human is `@bigboss`:

```bash
uvx hcom send --intent inform -- "@bigboss <result + what needs their call>"
```

That lands in their `tess inbox`. Escalations are automatic via `tess watch`.
