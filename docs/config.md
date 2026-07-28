# Config

[← README](../README.md)

Everything user-specific lives in `~/.config/tess/` — outside the repo — so `git pull` and the background auto-update never overwrite it.

```
~/.config/tess/
├── config          your repos, paths, fleet knobs (TESS_* vars)
├── models          local model tiers (small= / med= / big=)
├── modes/          overrides of the agent modes (think/post/boss/read/orchestrate)
├── templates/      your own role templates for `tess team`
└── commands/       an executable `foo` here → runs as `tess foo`
```

## `~/.config/tess/config`

```sh
TESS_WORKTREE_ROOT="$HOME/worktrees"    # where feature worktrees are created
TESS_CORE="$TESS_WORKTREE_ROOT/repos"   # where your source repos live

# A "fleet" is a set of repos that change together. Most people don't need one —
# run `tess new` inside any git repo and tess just uses that repo.
# TESS_REPOS="app api"
# TESS_REPOS_ALL="app api web"          # + optional ones (tess new --all)

# TESS_GIT_REMOTE="your-org"            # auto-clone missing fleet repos
# TESS_REPO_DIRS=""                     # extra roots for the repo map
# TESS_MAIN_BRANCH="main"

# TESS_TEST_CMD="npm test"              # run in each repo before `tess ship` pushes
# TESS_IDLE_STABLE_SECS=20              # idle time before escalation
# TESS_NOTIFY_CONTACT="Your Name"       # who `tess watch --phone` iMessages
# TESS_DEPLOY_DENY="Bash(terraform apply:*)"   # override the deploy deny-list

# TESS_VAULT="$HOME/Documents/notes"    # markdown notes vault (brain features)
# TESS_MAIL_FROM="you@work.com"         # default From for `tess mail send`

# TESS_NO_AUTOUPDATE=1                  # opt out of the background self-update
```

Environment always beats the config file, so a single command can be pointed at another root.

## Updates

tess self-updates with a background `git pull --ff-only`, throttled to once every 6h. It refuses to touch a dirty tree, so local hacking is never clobbered. Opt out with `TESS_NO_AUTOUPDATE=1`; `tess update` still works.

## Custom commands

```bash
tess commands new deploy    # scaffolds ~/.config/tess/commands/deploy and opens it
tess deploy                 # runs it; all TESS_* vars are available inside
```

These survive `tess update` — the repo never touches that folder.

## Optional dependencies

tess names the missing one when you reach for it.

| For | Install |
|---|---|
| the fleet | [uv](https://docs.astral.sh/uv) (tess runs [hcom](https://github.com/aannoo/hcom) via `uvx`) |
| nicer navigation | `fzf zoxide lazygit eza bat ripgrep chafa` |
| offline AI | [ollama](https://ollama.com) + a model |
| voice | `whisper-cpp` + `sox` + a speech model |

## Platform

Developed on **macOS**; CI runs the suite on Linux. The core — worktrees, sessions, fleet, todos, local AI — is portable Unix shell and Python 3 with no GNU/BSD assumptions.

**macOS-only** (marked in the menu): the connectors, `apps`/`login`/`startup`, `fix-files`. Windows is unsupported; WSL should work but isn't tested.
