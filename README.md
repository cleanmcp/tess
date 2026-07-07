# tess

**One command for your whole machine.** `tess` is a single CLI that ties together your code workflow, your notes/brain, your local AI, and your Mac's messages/calls/calendar — for you *and* for your AI coding agents (Claude Code, Kimi, etc.), who use it as their primary tool.

Type `tess` to see everything. Forget the rest.

```
tess                      the menu — everything you can do
tess new redis-fix        spin up isolated git worktrees across your repos
tess resume               resume any past Claude/Kimi session, in its folder
tess john                 read a note from your vault
tess messages alex        recent texts with a contact (by name)
tess local "explain X"    offline AI (local model, no internet)
tess read                 a reading companion for your current Apple Book
tess ask "what's on my calendar"   voice-routed answers
```

> Built for macOS + [cmux](https://cmux.com) (a Ghostty-based terminal). Most commands work in any terminal; worktree-opening and inline images are best in cmux.

---

## Install

```bash
git clone https://github.com/cleanmcp/tess.git
cd tess
./install.sh            # interactive: core + optional setup (all skippable)
# or: ./install.sh --minimal   for just the scripts
```

Then edit **`~/.config/tess/config`** to point at your notes vault and repos (see [Config](#config)). Make sure `~/.local/bin` is on your `PATH`.

`tess` degrades gracefully — anything you don't set up just isn't available; the rest works.

---

## What it does

### 🧠 Brain — your markdown vault (read/write, on demand)
Works with any markdown notes folder. The recommended app is **[Lokus](https://github.com/lokus-ai/lokus)** (the installer can grab it for you), but Obsidian or plain files work too. Nothing auto-loads, so it costs zero tokens until you ask.
```
tess <name>                  read a note (person / project / topic)
tess people | companies      rosters (from note tags/folders)
tess reminders               open follow-ups (unchecked - [ ] items)
tess add <name> -- <text>    append to a note (creates it)
tess person <name> -- <desc> add a contact note
tess log -- <text>           quick timestamped capture
tess brief                   your "what's going on now" note
```

### 🌳 Worktrees — multi-repo feature isolation
Spin up a matching git worktree across several repos at once, with env files copied in. Self-heals stale registrations.
```
tess new <feature>           worktrees for your default repos, opens in cmux
tess new --all <feature>     include optional repos
tess ls | rm | env | clean | branches
```

### 📋 Coding todos — one checklist across every session
A persistent coding to-do list (plain markdown checkboxes in `~/.config/tess/state/todos.md`). The open items are injected at the top of **every new agent session** via a `SessionStart` hook — so work survives the session that started it, and the next agent (or you) picks up where the last left off.
```
tess todo                    list open todos (add `all` to include done)
tess todo add [-p <proj>] <text>   add one (auto-tagged with the current repo)
tess todo done <id>          check it off   (reopen / rm / clear / edit)
```

### 🤖 AI agents
```
tess claude [feat] ["task"] [--model M --effort E]   spawn Claude in a worktree, task + settings VERIFIED applied
tess kimi   [feat] ["task"] [--model M --effort E]   same for Kimi (own models + thinking level)
tess resume                  resume ANY past Claude/Kimi session (any folder)
tess think | post            thinking-partner / content-partner modes
tess local | small | big     offline local models (ollama)
tess ask "<q>" | tess voice | tess listen    natural-language + hands-free voice
```
`--readonly` is enforced (plan mode), `--auto` starts straight in auto permission mode (no per-command approval prompts — footer-verified), deploy commands are denied unless `--can-deploy`, and `--budget N` is a hard USD cap. Every `--help` is safe — it never creates worktrees or spawns anything.

### 🚁 The fleet — many agents at once (you are `@bigboss`)
One tool drives the whole fleet; hcom is folded underneath (`tess hcom <anything>` for the rest).
```
tess team fleet.yaml         fan out N agents: per-agent worktree, prompt, model, effort,
                             role template (investigate/implement/review), count — --dry-run first
tess orchestrate "<goal>"    hire an AI lead: it decomposes, spawns, monitors, unblocks,
                             synthesizes, reports to you ('off' takes command back)
tess status | digest         fleet table (BLOCKED first) | everyone's last report, merged
tess report <agent>          one agent's FULL last message (scriptable)
tess inbox                   your unread mail from the fleet (cursor-tracked)
tess tell <agent|feat|all> -- <msg>   speak as @bigboss (agent-name @s in bodies auto-escaped)
tess wait <feat|all>         block until done — exit 2 means someone needs approval
tess watch on [--phone]      escalation daemon: BLOCKED / IDLE / DIED agents instantly ping
                             the lead's inbox — and your iPhone (TESS_NOTIFY_CONTACT)
tess approve <agent>         answer a blocked agent's approval dialog (shows it first)
tess inject <agent> -- <t>   force a prompt into its terminal — waits till ready, confirms it landed
tess diff <agent|feat>       what they actually changed (per-worktree diffstat)
tess ship <feat> [--merge]   diff → tests (TESS_TEST_CMD) → push → PR → optional squash-merge
tess done <feat>             one-shot teardown: kill its agents + panes + worktrees
tess spend                   budget ledger (spawn-time caps are enforced)
```

### 📱 Life (macOS, local, read-only unless you send)
```
tess messages [who]          recent iMessages/SMS incl. group chats (search by contact name)
tess chat <name|group>       full conversation thread + inline images
tess send <name> -- <msg>    send an iMessage
tess calls                   call log with contact names
tess calendar [days]         upcoming events (incl. recurring)
tess read                    reading companion for your current Apple Book
```

### 🩺 System + 🐾 fun
`tess doctor` (health), `tess disk`, `tess cheat`, and toys: `tess fish | bonsai | matrix | pipes | dex`.

---

## Config

`~/.config/tess/config` (created by the installer from `config.example`):

```sh
TESS_VAULT="$HOME/Documents/tess-vault"    # your markdown notes vault
TESS_HUB="$TESS_VAULT/hub"                  # where tess writes notes
TESS_WORKTREE_ROOT="$HOME/worktrees"        # feature worktrees
TESS_CORE="$TESS_WORKTREE_ROOT/repos"       # your source repos (one folder each)
TESS_REPOS="app api"                        # repos to fan out across
TESS_REPOS_ALL="app api web"                # + optional repos (tess new --all)
# TESS_GIT_REMOTE="https://github.com/your-org"   # optional auto-clone
```

Local model tiers live in `~/.config/tess/models` (`small=` / `med=` / `big=`).

---

## The "life" features need permissions (macOS)

These are **opt-in**. Grant only what you want; skip the rest.

| Feature | Permission | Where |
|---|---|---|
| `messages` `calls` `calendar` `read` | **Full Disk Access** for your terminal/cmux | System Settings → Privacy & Security → Full Disk Access |
| `send` | **Automation** (terminal → Messages) | Privacy & Security → Automation |
| `calendar` | **Calendars** (if prompted) | Privacy & Security → Calendars |
| `listen` | **Microphone** | prompts on first run |

Everything is **local** — messages, calls, and calendar are read from your Mac's own SQLite databases and never leave your machine.

---

## Optional dependencies

Installed by `./install.sh` if you say yes; each is optional:

- **CLI extras:** `fzf zoxide lazygit eza bat ripgrep chafa` (nicer navigation + inline images)
- **Offline AI:** [ollama](https://ollama.com) + a model (for `local`/`ask`/`voice`)
- **Voice:** `whisper-cpp` + `sox` + a speech model (for `listen`)
- **Multi-agent:** [hcom](https://github.com/aannoo/hcom) (for `agents` + coordination)

---

## Agent integration

`tess` is designed to be an agent's primary tool. Every interactive command **detects whether a human is present** — it prompts you, but when an agent runs it non-interactively it takes inline params and **fails with guidance instead of hanging**. Output is colored in a terminal and **plain when piped**, so agents get clean, parseable text.

Point your agents at it by adding a short section to their instructions (`CLAUDE.md`, `AGENTS.md`): tell them to run `tess` to discover commands and to pull/save context with `tess <name>` / `tess add` / `tess brief` on demand.

---

## License

MIT — see [LICENSE](LICENSE).

## Customizing (survives updates)

Everything user-specific lives in **`~/.config/tess/`** — *outside* the repo — so `git pull` (and the background auto-update) never overwrites it:

```
~/.config/tess/
├── config          # your paths, repos, startup apps (TESS_* vars)
├── models          # local model tiers
└── commands/       # your own commands: an executable `foo` here → run as `tess foo`
```

Add a custom command:
```bash
tess commands new deploy      # scaffolds ~/.config/tess/commands/deploy, opens it
# ...edit it...
tess deploy                   # runs it; TESS_* config vars are available inside
```

Custom commands show in `tess` under **🧩 YOUR COMMANDS** and are never clobbered by updates. To update tess itself: `tess update` (or it auto-pulls in the background). `--ff-only` means it also won't clobber the repo if you've hacked on it locally.
