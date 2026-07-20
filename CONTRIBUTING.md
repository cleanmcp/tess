# Contributing to tess

## Repo layout

```
bin/tess                the ONLY entrypoint on PATH — a bash dispatcher. It resolves the repo
                        through its own symlink and exports TESS_BIN / TESS_HOME / TESS_LIB.
libexec/                internal helpers, never on PATH, grouped by domain:
├── core/               help.sh · todo.sh · update.sh
├── worktrees/          worktree.sh (create/rm) · wt (wrapper, ls/prune/open) · repos.sh (repo map)
├── fleet/              spawn · team · orchestrate · hq (status/report/diff/approve) · watch ·
│                       comms (tell/inbox) · inject · done · ship · resume · loop
├── brain/              list (people/companies/reminders) · ask (NL router) · listen (voice)
├── life/               macOS layer: messages · chat · send · calls · cal · mail · music ·
│                       read · readpos · apps
└── lib/                shared python: tess_common.py (colors, Contacts) · tess_agents.py (hcom plumbing)
modes/                  system prompts for tess think/post/boss/read/orchestrate
templates/              built-in role templates for `tess team` (investigate/implement/review)
```

## Conventions

- **Nothing user-specific in the repo.** All personal state lives in `~/.config/tess/`
  (config, models, state/, commands/, templates/, modes/) — overrides beat repo copies,
  and `git pull` never touches them. If a change needs a machine-specific value, it goes
  through a `TESS_*` var with a sane default, documented in `config.example`.
- **Path resolution:** shell helpers find siblings relative to their own resolved location;
  python helpers add `../lib` to `sys.path` and honor `TESS_LIB`/`TESS_HOME` when set.
  Never hardcode `~/.local/bin` or an install location.
- **Interactive for humans, param-driven for agents.** Every command that would prompt must,
  when stdin is not a TTY, take inline params and fail with guidance instead of hanging.
  Output is colored on a TTY and plain when piped.
- **`--help` is always safe** — it must never create a worktree, spawn an agent, or mutate state.
- **Deterministic grammar.** Positional args never change meaning based on lookups or CWD in
  ways a user can't predict; ambiguity is an error (or an interactive picker), never a guess.
- **User-neutral language.** The user is "they/them" in prompts and comments; no personal
  names, playlists, repos, or app sets in code, defaults, or examples.
- Run `tests/smoke.sh` before pushing — it syntax-checks everything and runs the
  worktree battery in a temp dir (CI runs the same script).
