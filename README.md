# tess

**Session orchestration for AI development.** One terminal to spawn, watch, steer, and ship every stream of work an AI agent is doing for you — each in its own isolated session, none of them colliding or getting lost.

```
tess                         the menu — everything, one screen
tess claude redis-fix "cut p99 on the cache path"   spawn a session (own worktree, agent, context)
tess team fleet.yaml         fan out a whole fleet in one command
tess status                  the fleet at a glance — BLOCKED sessions first
tess ship redis-fix          diff → tests → push → PR, then tear it down
```

---

## You don't have an agent problem. You have a session problem.

Everyone can run an agent now. That's not the hard part.

The hard part shows up an hour later, when you look up and realize you're not running *an agent* — you're running a dozen half-finished **sessions**. Six terminals. Four branches mid-change. An agent from earlier you completely forgot about. Two of them editing the same file. Context you can't get back.

You've been doing session management by hand this whole time — badly — and never noticed that *was* the problem.

**tess makes the session the unit of work.** Every stream of work is a durable, isolated session — its own worktree, its own context and state, and the agent driving it — that you can spawn, watch, resume, steer, and ship, all from one place. The wedge isn't "run an agent." It's running *many* of them without losing the thread.

- **Isolation** — every session gets its own git worktree. No two agents fight over the same file.
- **Visibility** — one command shows the whole fleet: who's working, who's blocked, who's drifted, what each one changed.
- **Control** — steer a running session mid-flight, answer its approval prompts, or hand the whole fleet to an AI lead.
- **Shipping** — collect a finished session into a PR and tear it down in one command.

---

## Install

```bash
git clone https://github.com/cleanmcp/tess.git
cd tess
./install.sh              # interactive: core + optional setup (all skippable)
# or: ./install.sh --minimal    just the scripts, no prompts
```

Then make sure `~/.local/bin` is on your `PATH`, point `~/.config/tess/config` at your repos, and type `tess`.

Nothing you skip breaks anything else — tess degrades gracefully. Set up only what you use.

> **Platform.** The core (worktrees + the fleet + offline local AI) is cross-platform on any Unix shell. It's tuned for macOS and [cmux](https://cmux.com) (a Ghostty-based terminal) — worktree-opening and inline images are best there. The optional "life" features (messages/calls/calendar) are macOS-only.

---

## A session

A session is one worktree + one agent + the context it's holding. You spawn it with a name and a task; tess creates the isolated worktree, launches the agent in it, and **verifies** the task, model, and effort actually took before handing off.

```
tess claude <feature> "<task>"  [--model M] [--effort E] [--readonly] [--budget N]
tess kimi   <feature> "<task>"  …            same, for Kimi (its own models + thinking level)
tess resume                      resume ANY past session (any folder), picked by AI summary
```

Roles are **enforced**, not suggested: `--readonly` runs the agent in plan mode, deploy commands are denied unless `--can-deploy`, and `--budget N` is a hard USD cap. Every `--help` is safe — it never creates a worktree or spawns anything.

## The fleet — many sessions at once

One tool drives the whole fleet. You are `@bigboss`; the coordination backend is folded underneath.

```
tess team fleet.yaml         fan out N sessions from a YAML spec — each with its own worktree,
                             prompt, model, effort, and role (investigate/implement/review). --dry-run first.
tess orchestrate "<goal>"    hire an AI lead: it decomposes the goal, spawns sessions, monitors,
                             unblocks, synthesizes, and reports back. 'off' takes command back.

tess status                  fleet table — BLOCKED sessions first (--json for scripts)
tess digest                  everyone's last report, merged
tess diff <session>          what a session actually changed (per-worktree diffstat)
tess report <session>        one session's full last message

tess tell <session|all> -- <msg>    steer a running session (speaks as @bigboss)
tess inject <session> -- <text>     force a prompt into its terminal (waits, confirms it landed)
tess approve <session>              answer a blocked session's approval dialog
tess watch on [--phone]             escalation daemon: BLOCKED / IDLE / DIED sessions ping you instantly

tess ship <feature> [--merge]       diff → tests → push → PR → optional squash-merge
tess done <feature>                 one-shot teardown: kill its agents + panes + worktrees
tess spend                          budget ledger (spawn-time caps are enforced)
```

## Worktrees — the isolation layer

Sessions ride on git worktrees. You can also drive them directly for multi-repo feature work.

```
tess new <feature>           a matching worktree across your configured repos, env files copied in
tess new --all <feature>     include optional repos
tess ls | rm | env | clean | branches | wt | path
```

## Coding todos — one checklist across every session

A persistent, plain-markdown checklist. The open items are injected at the top of **every new agent session** via a `SessionStart` hook — so work survives the session that started it, and the next agent (or you) picks up where the last left off.

```
tess todo                    list open todos
tess todo add [-p <proj>] <text>   add one (auto-tagged with the current repo)
tess todo done <id>          check it off
```

---

## Run a fleet (60 seconds)

```bash
# 1. describe the work — one session per agent
cat > fleet.yaml <<'YAML'
defaults: { model: claude-sonnet-5, effort: high }
agents:
  - { name: cache,  feature: redis-cache,  role: implement,   prompt: "add a redis cache to the hot read path" }
  - { name: audit,  feature: sec-audit,    role: investigate, prompt: "audit auth middleware for authz gaps", readonly: true }
  - { name: flake,  feature: flaky-tests,  role: implement,   prompt: "find and fix the top 3 flaky tests" }
YAML

tess team fleet.yaml --dry-run     # see the exact spawn plan first
tess team fleet.yaml               # spawn all three — isolated worktrees, verified launch

tess status                        # watch them — BLOCKED first
tess approve audit                 # unblock one when it asks
tess ship redis-cache --merge      # ship the one that's done
tess done redis-cache              # tear it down
```

---

## Optional: the personal layer

tess grew out of one developer's whole-machine setup, so it also ships a **brain** (a markdown notes vault) and **life** (macOS messages/calls/calendar) layer. These are **entirely optional** — off until you configure them, and they stay out of the way if you don't. They cost zero tokens and never auto-load.

**Brain** — any markdown notes folder (Obsidian, [Lokus](https://github.com/lokus-ai/lokus), or plain files). Read/write on demand:

```
tess <name>                  read a note        tess add <name> -- <text>    append to a note
tess people | companies      rosters            tess brief                   your "what's going on" note
```

**Life** (macOS, local, read-only unless you send) — reads your Mac's own SQLite databases; nothing leaves your machine:

```
tess messages [who]   tess chat <name>   tess send <name> -- <msg>   tess calls   tess calendar [days]
```

These need macOS permissions you grant yourself (Full Disk Access for reads; Automation for `send`). Skip them and the core is untouched.

---

## Config

Everything user-specific lives in **`~/.config/tess/`** — *outside* the repo — so `git pull` (and the background auto-update) never overwrites it.

```sh
# ~/.config/tess/config   (created by the installer from config.example)
TESS_WORKTREE_ROOT="$HOME/worktrees"        # where feature worktrees are created
TESS_CORE="$TESS_WORKTREE_ROOT/repos"       # where your source repos live (one folder each)
TESS_REPOS="app api"                        # default repos to fan out across
TESS_REPOS_ALL="app api web"                # + optional repos (tess new --all)
# TESS_GIT_REMOTE="https://github.com/your-org"   # optional: auto-clone missing repos
# TESS_TEST_CMD="npm test"                        # run in each repo before `tess ship` pushes
# TESS_VAULT="$HOME/Documents/notes"              # optional: a markdown notes vault (brain features)
```

```
~/.config/tess/
├── config          # your repos, paths, fleet knobs (TESS_* vars)
├── models          # local model tiers (small= / med= / big=)
├── templates/      # your own role templates for `tess team`
└── commands/       # your own commands: an executable `foo` here → run as `tess foo`
```

Add a custom command:
```bash
tess commands new deploy      # scaffolds ~/.config/tess/commands/deploy, opens it
tess deploy                   # runs it; TESS_* config vars are available inside
```

Custom commands and config survive `tess update` (and the background auto-pull). `--ff-only` means an update won't clobber the repo if you've hacked on it locally.

---

## Optional dependencies

Installed by `./install.sh` if you say yes; each is optional:

- **Fleet backend:** [hcom](https://github.com/aannoo/hcom) — tess runs it via `uvx hcom` out of the box if you have [uv](https://docs.astral.sh/uv).
- **CLI extras:** `fzf zoxide lazygit eza bat ripgrep chafa` (nicer navigation + inline images)
- **Offline AI:** [ollama](https://ollama.com) + a model (for `tess local` / `ask` / `voice`)
- **Voice:** `whisper-cpp` + `sox` + a speech model (for `tess listen`)

---

## Agents use tess too

tess is designed to be an agent's primary tool. Every interactive command **detects whether a human is present** — it prompts you, but when an agent runs it non-interactively it takes inline params and **fails with guidance instead of hanging**. Output is colored in a terminal and **plain when piped**, so agents get clean, parseable text.

The installer wires a short primer into your agents' instructions (`CLAUDE.md`, `AGENTS.md`) telling them to run `tess` to discover commands and to go through tess for worktrees and coordination rather than raw `git worktree` / backend calls.

---

## License

MIT — see [LICENSE](LICENSE).
