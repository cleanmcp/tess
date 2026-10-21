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

## Move a session to another machine

```bash
tess handoff                     what's parked where
tess handoff mini                send this folder's newest session to the peer "mini"
tess handoff mini --pick         choose any past session first
tess handoff mini --dry-run      print the plan, touch nothing
tess handoff back [mini]         take it back
```

Configure peers first — nothing is guessed:

```bash
TESS_PEERS="mini=mac-mini  box=dev@10.0.0.5"     # ~/.config/tess/config
```

Each target is anything `ssh` accepts (a Host alias, `user@host`, or `host`) reachable with
key-based auth. Both machines need `tess`, `git` and `rsync`; the folder lands at the same
path relative to `$HOME`.

A session is three things, and each travels the way that suits it:

| part | how it moves |
|---|---|
| code | one throwaway WIP commit, pushed over ssh to a neutral ref, soft-reset on arrival — git sends only the delta and the working tree lands byte-identical, uncommitted edits included |
| env | `.env*` files rsynced beside it (gitignored, so no commit can carry them) |
| context | the agent transcript, rsynced with every absolute path rewritten for the peer's `$HOME` |

**It's a baton, not a mirror.** Exactly one machine holds a session at a time: the source is
parked with a `.tess-handoff` marker, so the two sides can't diverge and there is no merge
step. Handing off a folder that is already parked is an error, and the transcript is
append-only with only the holder appending. Nothing is destructive — the WIP commit is
soft-reset on both ends, so an interrupted handoff leaves the working tree as it was.

If the peer has the repo but not the worktree, handoff creates it there with `tess new` and
moves it onto the session's branch. A multi-repo feature root can't travel as one unit —
hand off one repo at a time.

## Reporting back, as an agent

The human is `@bigboss`:

```bash
uvx hcom send --intent inform -- "@bigboss <result + what needs their call>"
```

That lands in their `tess inbox`. Escalations are automatic via `tess watch`.
